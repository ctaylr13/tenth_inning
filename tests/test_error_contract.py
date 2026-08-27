"""Regression tests for the Phase 1 error contract.

Each test maps to a failure mode from the inventory. The point of this file is
that the contract can't silently rot: re-adding a bare `except Exception`, or
letting a traceback into a response body, breaks a test here.

No server and no port required -- TestClient talks to the ASGI app in-process,
which also sidesteps the Docker-on-8000 collision entirely.
"""

import duckdb
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

import server
from errors import ErrorCode

# raise_server_exceptions=False makes TestClient behave like a real server:
# unhandled exceptions go through handle_unexpected instead of being re-raised
# into the test. Without this the safety-net test fails confusingly.
client = TestClient(server.app, raise_server_exceptions=False)

REQUEST_ID_HEADER = "X-Request-ID"


# A route that always blows up, so we can prove the safety net catches our bugs.
@server.app.get("/__test_boom")
def _boom():
    return 1 / 0


def envelope(response):
    """Pull the error envelope out, asserting it's actually shaped like one."""
    body = response.json()
    assert set(body) == {"error"}, f"expected only an 'error' key, got {list(body)}"
    err = body["error"]
    assert set(err) == {"code", "message", "details", "request_id"}
    return err


# --- the happy path ---------------------------------------------------------


def test_schedule_returns_200_and_a_list():
    r = client.get("/api/schedule")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_zero_games_would_be_200_not_204():
    """An empty schedule is an empty state, not an error and not a 204.

    204 means "no body at all", which makes res.json() throw on the client.
    An empty collection is a 200 carrying [].
    """
    r = client.get("/api/schedule")
    assert r.status_code == 200
    assert r.status_code != 204


# --- 4xx: the client sent something wrong -----------------------------------


def test_unmatched_url_is_enveloped_not_fastapi_default():
    """The handler everyone forgets.

    Without a StarletteHTTPException handler this returns {"detail": "Not Found"}
    and silently breaks the contract for every typo'd URL.
    """
    r = client.get("/nope")
    assert r.status_code == 404
    assert envelope(r)["code"] == ErrorCode.ROUTE_NOT_FOUND.value
    assert "detail" not in r.json()


def test_wrong_method_is_route_not_found_not_validation():
    """A route is a path plus a method. Nothing about the payload was wrong."""
    r = client.delete("/api/schedule")
    assert r.status_code == 405
    assert envelope(r)["code"] == ErrorCode.ROUTE_NOT_FOUND.value


def test_bad_body_type_is_422_with_field_details():
    r = client.put("/api/watchhistory", json=[{"gamePk": "banana", "watched": True}])
    assert r.status_code == 422
    err = envelope(r)
    assert err["code"] == ErrorCode.VALIDATION_FAILED.value
    fields = err["details"]["fields"]
    assert any("gamePk" in f["field"] for f in fields)


def test_empty_list_is_400():
    """This code carries 400 here and 422 elsewhere -- a deliberate choice."""
    r = client.put("/api/watchhistory", json=[])
    assert r.status_code == 400
    assert envelope(r)["code"] == ErrorCode.VALIDATION_FAILED.value


def test_duplicate_gamepk_is_409_and_names_the_duplicates():
    r = client.put(
        "/api/watchhistory",
        json=[{"gamePk": 777, "watched": True}, {"gamePk": 777, "watched": False}],
    )
    assert r.status_code == 409
    err = envelope(r)
    assert err["code"] == ErrorCode.DUPLICATE_WATCH_ENTRY.value
    assert err["details"]["duplicates"] == [777]


def test_a_valid_payload_is_not_rejected_as_duplicate():
    """Guard against the duplicate check being too eager."""
    r = client.put(
        "/api/watchhistory",
        json=[{"gamePk": 777, "watched": True}, {"gamePk": 778, "watched": True}],
    )
    assert r.status_code == 200


# --- 5xx: we broke ----------------------------------------------------------


def test_unhandled_exception_is_500_not_422():
    """The request was fine; *we* broke. That is always a 500.

    Not a 422 (that describes the client's payload) and not a 502 (that would
    mean we're a gateway and something behind us failed).
    """
    r = client.get("/__test_boom")
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value


def test_500_response_leaks_nothing():
    """The client gets a request id. The traceback goes to the logs."""
    r = client.get("/__test_boom")
    body = r.text
    for leak in ("ZeroDivision", "Traceback", "server.py", "division by zero"):
        assert leak not in body, f"response leaked {leak!r}"


def test_missing_database_file_is_500(monkeypatch):
    """No retry ever fixes a missing file, so it is a 500, not a 503.

    duckdb.connect() creates a missing file instead of raising, so without the
    explicit guard this surfaces later as a confusing "table missing" instead.
    """
    monkeypatch.setattr(server, "DB_PATH", "definitely_not_here.duckdb")
    r = client.get("/api/schedule")
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value


def test_locked_database_is_503(monkeypatch):
    """DuckDB is single-writer. A retry in 200ms plausibly succeeds -> 503."""

    def locked(*args, **kwargs):
        raise duckdb.IOException("Could not set lock on file")

    monkeypatch.setattr(server.duckdb, "connect", locked)
    r = client.get("/api/schedule")
    assert r.status_code == 503
    assert envelope(r)["code"] == ErrorCode.DATA_SOURCE_UNAVAILABLE.value


def test_duckdb_is_opened_read_only():
    conn = server.get_conn()
    try:
        with pytest.raises(duckdb.InvalidInputException):
            conn.execute("CREATE TABLE should_never_exist (id INTEGER)")
    finally:
        conn.close()


def test_missing_table_is_500_not_404(tmp_path, monkeypatch):
    """Our schema being broken is our fault. The client's URL was valid.

    404 answers "does the URL you asked for exist?" -- it does. So 500.
    """
    empty = tmp_path / "empty.duckdb"
    duckdb.connect(str(empty)).close()
    monkeypatch.setattr(server, "DB_PATH", str(empty))

    r = client.get("/api/schedule")
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value


# --- the write path's own error branches ------------------------------------


class _FailingPgEngine:
    """Stands in for pg_engine -- every execute() raises the given exc."""

    def __init__(self, exc):
        self.exc = exc
        self.rolled_back = False

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.rolled_back = True
        return False

    def execute(self, *args, **kwargs):
        raise self.exc


PAYLOAD = [{"gamePk": 777, "watched": True}]


def _put_with_failing_pg(monkeypatch, exc):
    engine = _FailingPgEngine(exc)
    monkeypatch.setattr(server, "pg_engine", engine)
    return client.put("/api/watchhistory", json=PAYLOAD), engine


def test_locked_database_during_write_is_503(monkeypatch):
    exc = OperationalError("INSERT ...", {}, Exception("could not connect"))
    r, _ = _put_with_failing_pg(monkeypatch, exc)
    assert r.status_code == 503
    assert envelope(r)["code"] == ErrorCode.DATA_SOURCE_UNAVAILABLE.value


def test_missing_table_during_write_is_500(monkeypatch):
    exc = ProgrammingError(
        "INSERT ...", {}, Exception('relation "watch_history" does not exist')
    )
    r, _ = _put_with_failing_pg(monkeypatch, exc)
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value


def test_unexpected_write_failure_is_500_and_leaks_nothing(monkeypatch):
    """The regression guard for the original bug.

    A bare `except Exception` that re-raises as HTTPException(500, str(e)) puts
    the exception text -- table names, paths, query structure -- in the body.
    """
    secret = "internal_table_name_xyz"
    r, _ = _put_with_failing_pg(monkeypatch, RuntimeError(secret))
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value
    assert secret not in r.text


def test_failed_write_is_rolled_back(monkeypatch):
    """A half-written transaction must not survive the error."""
    _, engine = _put_with_failing_pg(monkeypatch, RuntimeError("boom"))
    assert engine.rolled_back


# --- request ids ------------------------------------------------------------


def test_client_supplied_request_id_is_preserved():
    """Lets the frontend mint an id, log it, and hand you something to grep."""
    r = client.get("/__test_boom", headers={REQUEST_ID_HEADER: "my-test-123"})
    assert envelope(r)["request_id"] == "my-test-123"
    assert r.headers[REQUEST_ID_HEADER] == "my-test-123"


def test_request_id_is_generated_when_absent():
    r = client.get("/__test_boom")
    rid = envelope(r)["request_id"]
    assert rid and rid != "-"
    assert r.headers[REQUEST_ID_HEADER] == rid


def test_request_id_is_on_successful_responses_too():
    r = client.get("/api/schedule")
    assert r.headers.get(REQUEST_ID_HEADER)


# --- the contract itself ----------------------------------------------------

# fmt: off
# One row per failure mode -- the table is the point, so it stays compact.
ERROR_REQUESTS = [
    ("unmatched url", lambda: client.get("/nope")),
    ("bad body", lambda: client.put("/api/watchhistory", json=[{"gamePk": "x", "watched": True}])),
    ("empty list", lambda: client.put("/api/watchhistory", json=[])),
    ("duplicates", lambda: client.put(
        "/api/watchhistory",
        json=[{"gamePk": 1, "watched": True}, {"gamePk": 1, "watched": True}])),
    ("our bug", lambda: client.get("/__test_boom")),
    ("wrong method", lambda: client.delete("/api/schedule")),
]
# fmt: on


@pytest.mark.parametrize("label,make_request", ERROR_REQUESTS, ids=[r[0] for r in ERROR_REQUESTS])  # fmt: skip
def test_every_error_uses_the_same_envelope(label, make_request):
    """The whole point: one shape, a known code, a request id -- every time.

    If any failure path escapes the envelope, the frontend's switch(error.code)
    silently falls through to the generic branch, and this test is what catches
    it before a user does.
    """
    r = make_request()
    assert r.status_code >= 400
    err = envelope(r)
    assert err["code"] in {c.value for c in ErrorCode}
    assert isinstance(err["message"], str) and err["message"]
    assert isinstance(err["details"], dict)
    assert err["request_id"]


# --- the read endpoints' validation -----------------------------------------
#
# The point of these routes is that a request can now be wrong in ways a body
# can't be: a month outside the season, an unknown enum, a negative offset, an
# id that parses but names nothing. Each one has to land in the same envelope.


def test_games_list_pages_and_reports_total():
    r = client.get("/api/games")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 50 and body["offset"] == 0
    assert [g["gamePk"] for g in body["items"]] == [777, 778, 779]


def test_games_filters_compose():
    assert client.get("/api/games?month=3").json()["total"] == 2
    assert client.get("/api/games?result=win").json()["total"] == 2
    assert client.get("/api/games?result=win&month=3").json()["total"] == 1
    assert client.get("/api/games?watched=true").json()["total"] == 1


def test_offset_past_the_end_is_an_empty_page_not_an_error():
    """Paging off the end is a legitimate request with nothing in it."""
    r = client.get("/api/games?offset=99")
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 3


def test_a_filter_matching_nothing_is_200_not_404():
    """No August games is an empty result, not a missing resource."""
    r = client.get("/api/games?month=8")
    assert r.status_code == 200
    assert r.json()["total"] == 0


BAD_QUERIES = [
    ("month too high", "/api/games?month=13", "month"),
    ("month too low", "/api/games?month=2", "month"),
    ("month not a number", "/api/games?month=banana", "month"),
    ("unknown result enum", "/api/games?result=tie", "result"),
    ("limit below range", "/api/games?limit=0", "limit"),
    ("limit above range", "/api/games?limit=500", "limit"),
    ("negative offset", "/api/games?offset=-1", "offset"),
    ("watched not a bool", "/api/games?watched=maybe", "watched"),
    ("path id not a number", "/api/games/abc", "gamePk"),
    ("path id not positive", "/api/games/0", "gamePk"),
]


@pytest.mark.parametrize("label,url,field", BAD_QUERIES, ids=[b[0] for b in BAD_QUERIES])  # fmt: skip
def test_bad_parameters_are_422_naming_the_field(label, url, field):
    r = client.get(url)
    assert r.status_code == 422
    err = envelope(r)
    assert err["code"] == ErrorCode.VALIDATION_FAILED.value
    assert [f["field"] for f in err["details"]["fields"]] == [field]
    assert err["details"]["fields"][0]["reason"]


def test_field_paths_drop_the_location_prefix():
    """`field` means the parameter, whether it came from the query or a body.

    FastAPI prefixes loc with "query"/"path"/"body"; leaving it on for some and
    stripping it for others would make the same key mean two different things.
    """
    q = client.get("/api/games?month=13")
    assert envelope(q)["details"]["fields"][0]["field"] == "month"

    b = client.put("/api/watchhistory", json=[{"gamePk": "x", "watched": True}])
    assert envelope(b)["details"]["fields"][0]["field"] == "0.gamePk"


def test_known_game_returns_detail():
    r = client.get("/api/games/777")
    assert r.status_code == 200
    body = r.json()
    assert body["gamePk"] == 777
    assert body["away_team_name"] == "Texas Rangers"
    assert body["watched"] is True


def test_unknown_game_is_resource_not_found_not_route_not_found():
    """The route exists and the id parsed -- only the row is missing.

    ROUTE_NOT_FOUND would tell the client it built a bad URL, which is a
    different bug and a different thing for the UI to say.
    """
    r = client.get("/api/games/424242")
    assert r.status_code == 404
    err = envelope(r)
    assert err["code"] == ErrorCode.RESOURCE_NOT_FOUND.value
    assert err["details"]["gamePk"] == 424242


def test_linescore_returns_innings_in_order():
    r = client.get("/api/games/777/linescore")
    assert r.status_code == 200
    body = r.json()
    assert body["gamePk"] == 777
    assert [i["inning_num"] for i in body["innings"]] == [1, 2]
    assert body["innings"][0]["home_runs"] == 2


def test_game_with_no_innings_is_an_empty_list_not_a_404():
    """The game exists; nothing was recorded. That is not a missing resource."""
    r = client.get("/api/games/779/linescore")
    assert r.status_code == 200
    assert r.json()["innings"] == []


def test_linescore_for_unknown_game_is_404():
    r = client.get("/api/games/424242/linescore")
    assert r.status_code == 404
    assert envelope(r)["code"] == ErrorCode.RESOURCE_NOT_FOUND.value
