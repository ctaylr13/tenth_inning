"""The SSE live layer.

The point of these tests is the seam the whole transport turns on: a failure
raised BEFORE the first byte is an ordinary HTTP error with the full envelope,
and everything after it has to arrive as an event instead. If the 404 test ever
starts returning 200 with an error event, the existence check has drifted into
the generator.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def fast_ticker():
    """Replay at full speed. The interval is the thing under test exactly once
    (that events arrive at all), never how long they take."""
    original = server.broadcaster.interval
    server.broadcaster.interval = 0.01
    yield
    server.broadcaster.interval = original


# A stream that never sends a terminal event also never closes, so an
# unbounded drain turns a bug into a hung test run instead of a failure.
READ_TIMEOUT_SECONDS = 5.0


def read_events(gamePk: int, url: str | None = None) -> list[tuple[str, dict]]:
    """Drain one SSE stream into [(event, data), ...]."""
    events: list[tuple[str, dict]] = []
    deadline = time.monotonic() + READ_TIMEOUT_SECONDS

    with client.stream("GET", url or f"/api/live/{gamePk}") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        event = None
        for line in response.iter_lines():
            if time.monotonic() > deadline:
                raise AssertionError(
                    f"stream did not terminate within {READ_TIMEOUT_SECONDS}s; "
                    f"got {[kind for kind, _ in events]}"
                )
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((event, json.loads(line.removeprefix("data: "))))
    return events


# --- before the first byte: still ordinary HTTP ------------------------------
def test_unknown_game_is_a_404_with_the_full_envelope():
    """The whole reason the existence check is not inside the generator."""
    response = client.get("/api/live/999999")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "RESOURCE_NOT_FOUND"
    assert error["details"]["gamePk"] == 999999
    # Same contract as every other route: an id to grep for.
    assert error["request_id"]
    assert response.headers["X-Request-ID"] == error["request_id"]


def test_unparseable_gamePk_is_a_422_before_the_route_runs():
    assert client.get("/api/live/banana").status_code == 422


def test_zero_gamePk_fails_the_gt_constraint():
    assert client.get("/api/live/0").status_code == 422


# --- after the first byte: events only ---------------------------------------
def test_replays_every_inning_in_order_then_ends():
    events = read_events(777)
    kinds = [kind for kind, _ in events]

    assert kinds == ["open", "inning", "inning", "end"]

    opened = events[0][1]
    assert opened["gamePk"] == 777
    assert opened["request_id"]  # SSE is still HTTP, so the middleware ran

    innings = [payload for kind, payload in events if kind == "inning"]
    assert [i["seq"] for i in innings] == [1, 2]
    assert [i["inning"]["inning_num"] for i in innings] == [1, 2]
    assert innings[0]["inning"]["home_runs"] == 2

    assert events[-1][1]["innings"] == 2


def test_game_with_no_innings_ends_immediately_and_is_not_an_error():
    """gamePk 779 exists but has nothing recorded. That is an empty state."""
    events = read_events(779)

    assert [kind for kind, _ in events] == ["open", "end"]
    assert events[-1][1]["innings"] == 0


# --- the fan-out --------------------------------------------------------------
def test_subscribers_are_released_when_the_stream_finishes():
    """A ticker left running for nobody is the leak this guards against."""
    read_events(777)
    assert server.broadcaster.subscriber_count(777) == 0


def test_ticker_reads_the_database_once_no_matter_how_many_innings():
    """Polling costs one read per client per tick; the ticker costs one read,
    full stop. That difference is the entire argument for a live layer."""
    calls = []
    original = server.broadcaster._load
    server.broadcaster._load = lambda gamePk: (calls.append(gamePk), original(gamePk))[
        1
    ]
    try:
        events = read_events(777)
    finally:
        server.broadcaster._load = original

    assert len([k for k, _ in events if k == "inning"]) == 2
    assert calls == [777]


# --- failures past the first byte --------------------------------------------
def test_loader_failure_arrives_as_a_failure_event_not_a_500():
    """Once the stream is open the status code is committed at 200, so a broken
    database has to be delivered in-band or the client just sees silence."""

    def boom(gamePk):
        raise RuntimeError("duckdb exploded")

    original = server.broadcaster._load
    server.broadcaster._load = boom
    try:
        events = read_events(778)
    finally:
        server.broadcaster._load = original

    assert [kind for kind, _ in events] == ["open", "failure"]

    payload = events[-1][1]["error"]
    # Same envelope shape as the HTTP path, so errors.ts can share its switch.
    assert payload["code"] == "DATA_SOURCE_UNAVAILABLE"
    assert payload["request_id"]
    assert set(payload) == {"code", "message", "details", "request_id"}
