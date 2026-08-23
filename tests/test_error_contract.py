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
#
# The tests above patch duckdb.connect, so they fail inside get_conn() and never
# enter update_watchhistory's try block. These drive a connection that fails
# mid-transaction, which is the only way to cover its except branches -- without
# them, re-adding `except Exception: raise HTTPException(500, str(e))` passes.


class _FailingConn:
    """A connection that raises on any real statement, but lets ROLLBACK through."""

    def __init__(self, exc):
        self.exc = exc
        self.rolled_back = False

    def execute(self, sql, *args, **kwargs):
        if sql.strip().upper().startswith("ROLLBACK"):
            self.rolled_back = True
            return self
        raise self.exc

    def register(self, *a, **k):
        pass

    def unregister(self, *a, **k):
        pass

    def close(self):
        pass


PAYLOAD = [{"gamePk": 777, "watched": True}]


def _put_with_failing_conn(monkeypatch, exc):
    conn = _FailingConn(exc)
    monkeypatch.setattr(server, "get_conn", lambda: conn)
    return client.put("/api/watchhistory", json=PAYLOAD), conn


def test_locked_database_during_write_is_503(monkeypatch):
    r, _ = _put_with_failing_conn(monkeypatch, duckdb.IOException("lock"))
    assert r.status_code == 503
    assert envelope(r)["code"] == ErrorCode.DATA_SOURCE_UNAVAILABLE.value


def test_missing_table_during_write_is_500(monkeypatch):
    r, _ = _put_with_failing_conn(monkeypatch, duckdb.CatalogException("no table"))
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value


def test_unexpected_write_failure_is_500_and_leaks_nothing(monkeypatch):
    """The regression guard for the original bug.

    A bare `except Exception` that re-raises as HTTPException(500, str(e)) puts
    the exception text -- table names, paths, query structure -- in the body.
    """
    secret = "internal_table_name_xyz"
    r, _ = _put_with_failing_conn(monkeypatch, RuntimeError(secret))
    assert r.status_code == 500
    assert envelope(r)["code"] == ErrorCode.INTERNAL_ERROR.value
    assert secret not in r.text


def test_failed_write_is_rolled_back(monkeypatch):
    """A half-written transaction must not survive the error."""
    _, conn = _put_with_failing_conn(monkeypatch, RuntimeError("boom"))
    assert conn.rolled_back


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
