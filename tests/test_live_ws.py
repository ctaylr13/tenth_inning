"""The websocket live layer.

A websocket has no status line the browser can read -- not for a bad gamePk,
not for a missing game, not for a database that fell over. So every assertion
here is a version of one question: did the envelope survive the trip, and can
the client still tell the three apart? The ticker underneath is the same object
the SSE route uses, unchanged.
"""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_live_sse import read_events

import error_handlers
import server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def fast_ticker():
    original = server.broadcaster.interval
    server.broadcaster.interval = 0.01
    yield
    server.broadcaster.interval = original


# The replayed games have 2 innings, so anything past this means the server is
# sending frames it should not and the drain would never end on its own.
MAX_FRAMES = 20


def drain(websocket) -> tuple[list[dict], int | None]:
    """Read one socket to completion. The close code is returned too because it
    is all an intermediary ever sees -- checking only frames would pass while
    the wire lied."""
    frames: list[dict] = []
    while len(frames) <= MAX_FRAMES:
        message = websocket.receive()
        if message["type"] == "websocket.close":
            return frames, message.get("code")
        frames.append(json.loads(message["text"]))
    raise AssertionError(f"socket never closed; got {[f['type'] for f in frames]}")


def read_frames(gamePk: int | str) -> tuple[list[dict], int | None]:
    with client.websocket_connect(f"/api/live/ws/{gamePk}") as websocket:
        return drain(websocket)


# --- the happy path -----------------------------------------------------------
def test_replays_every_inning_in_order_then_closes_clean():
    frames, close_code = read_frames(777)

    assert [f["type"] for f in frames] == ["open", "inning", "inning", "end"]
    assert [f["seq"] for f in frames if f["type"] == "inning"] == [1, 2]
    assert frames[1]["inning"]["home_runs"] == 2
    assert frames[-1]["innings"] == 2
    assert close_code == server.WS_NORMAL_CLOSURE


def test_the_request_id_is_minted_in_the_route_not_by_the_middleware():
    """RequestIDMiddleware only wraps "http" scopes, so nothing upstream made an
    id. It travels in a frame because the handshake's response headers are not
    exposed to the browser at all."""
    frames, _ = read_frames(777)

    assert frames[0]["type"] == "open"
    assert frames[0]["request_id"]


def test_game_with_no_innings_ends_immediately_and_is_not_an_error():
    """Same rule as every other transport: gamePk 779 exists with nothing
    recorded, and that is an empty state."""
    frames, close_code = read_frames(779)

    assert [f["type"] for f in frames] == ["open", "end"]
    assert frames[-1]["innings"] == 0
    assert close_code == server.WS_NORMAL_CLOSURE


# --- the degradation: failures that used to be status codes -------------------
def test_unknown_game_is_a_frame_now_not_a_404():
    """The headline cost. The status line was spent on the handshake, so the
    identical error is hand-delivered as a message and the close code is a clean
    1000 -- indistinguishable from success on the wire."""
    frames, close_code = read_frames(999999)

    assert [f["type"] for f in frames] == ["failure"]
    error = frames[0]["error"]
    assert error["code"] == "RESOURCE_NOT_FOUND"
    assert error["details"]["gamePk"] == 999999
    assert error["request_id"]
    assert close_code == server.WS_NORMAL_CLOSURE

    # Byte for byte the envelope the HTTP route sends, minus the id, which is
    # per-connection. If these drift, errors.ts needs two switches.
    http_error = client.get("/api/games/999999").json()["error"]
    assert error["code"] == http_error["code"]
    assert error["message"] == http_error["message"]
    assert error["details"] == http_error["details"]


def test_unparseable_gamePk_is_reshaped_not_raw_pydantic():
    """FastAPI's default leaks pydantic's raw error list as the close reason.
    handle_websocket_validation_error sends the same reshaped fields the HTTP
    path sends instead."""
    frames, close_code = read_frames("banana")

    assert [f["type"] for f in frames] == ["failure"]
    error = frames[0]["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["fields"] == [
        {
            "field": "gamePk",
            "reason": "Input should be a valid integer, "
            "unable to parse string as an integer",
        }
    ]
    assert error["request_id"]
    # 1008 is the entire 4xx range on this transport.
    assert close_code == error_handlers.WS_POLICY_VIOLATION


def test_a_broken_database_arrives_as_a_frame_not_a_dropped_socket():
    """The read happens after accept(), so an AppError raised there has no status
    line left to travel on. It reaches the handlers anyway -- Starlette passes a
    WebSocket where a Request would be -- and _deliver puts it in a frame.

    Regression: this used to raise out of the route, and the handler then died on
    `request.method`, so the client got a dropped socket and the log got an
    AttributeError instead of the real cause."""
    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(server, "DB_PATH", "/nonexistent/redsox_25.duckdb")
    try:
        frames, close_code = read_frames(777)
    finally:
        monkeypatched.undo()

    assert [f["type"] for f in frames] == ["failure"]
    error = frames[0]["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["request_id"]
    assert close_code == error_handlers.WS_INTERNAL_ERROR


def test_a_ticker_failure_carries_its_own_id_not_the_connections():
    """Two id sources, on purpose. _close_with_error reuses what the route parked
    on websocket.state, so one connection has one id. The ticker cannot: it fans
    one failure out to every subscriber, and no single connection owns it."""
    original = server.broadcaster._load

    def boom(gamePk):
        raise RuntimeError("duckdb exploded")

    server.broadcaster._load = boom
    try:
        frames, _ = read_frames(778)
    finally:
        server.broadcaster._load = original

    opened, failed = frames
    assert opened["type"] == "open"
    assert failed["type"] == "failure"
    assert failed["error"]["request_id"] != opened["request_id"]


def test_zero_gamePk_fails_the_gt_constraint():
    frames, _ = read_frames(0)

    assert frames[0]["error"]["code"] == "VALIDATION_FAILED"
    assert frames[0]["error"]["details"]["fields"][0]["field"] == "gamePk"


def test_loader_failure_arrives_as_a_frame_and_closes_1011():
    """1011 is as close as RFC 6455 gets to a 5xx. The frame still carries the
    real code, because 1011 does not tell the client whether a retry can win."""

    def boom(gamePk):
        raise RuntimeError("duckdb exploded")

    original = server.broadcaster._load
    server.broadcaster._load = boom
    try:
        frames, close_code = read_frames(778)
    finally:
        server.broadcaster._load = original

    assert [f["type"] for f in frames] == ["open", "failure"]
    error = frames[-1]["error"]
    assert error["code"] == "DATA_SOURCE_UNAVAILABLE"
    assert set(error) == {"code", "message", "details", "request_id"}
    assert close_code == server.WS_INTERNAL_ERROR


def test_route_not_found_is_still_a_handshake_rejection():
    """No route matched, so nothing can accept the socket. Pinned because it is
    what the client's "closed with nothing" fallback exists for."""
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/api/live/ws/777/nope"),
    ):
        pass


# --- the fan-out --------------------------------------------------------------
def test_subscribers_are_released_when_the_stream_finishes():
    read_frames(777)
    assert server.broadcaster.subscriber_count(777) == 0


def test_a_client_that_hangs_up_early_stops_the_ticker():
    """What _ws_wait_for_disconnect is for -- a send-only loop parked on
    queue.get() would otherwise keep replaying to nobody."""
    with client.websocket_connect("/api/live/ws/777") as websocket:
        websocket.receive()  # open
        assert server.broadcaster.subscriber_count(777) == 1

    assert server.broadcaster.subscriber_count(777) == 0


# One ticker serving two clients is asserted in test_broadcaster.py: each
# TestClient websocket session runs the app in its own event loop, so the
# ticker's put_nowait lands on a queue whose loop never wakes and the test
# hangs. Real uvicorn has one loop.


# --- parity with SSE ----------------------------------------------------------
def test_the_two_transports_send_the_same_payloads():
    """The frames are the contract now, so the two must not fork. Only the
    per-connection request_id is allowed to differ."""
    sse = read_events(777)
    ws, _ = read_frames(777)

    assert [kind for kind, _ in sse] == [frame["type"] for frame in ws]

    for (kind, sse_payload), ws_frame in zip(sse, ws, strict=True):
        assert ws_frame.pop("type") == kind

        # Every message the ticker publishes already stamps its own type -- it
        # has to, so a transport with no event names can still route it -- and
        # _sse then serializes that dict whole, naming the type twice. `open` is
        # the exception: the SSE route builds it and leans on the `event:` line
        # alone. So it is the only frame the websocket had to name itself.
        if kind == "open":
            assert "type" not in sse_payload
        else:
            assert sse_payload.pop("type") == kind

        # Minted per connection, so these two legitimately differ.
        sse_payload.pop("request_id", None)
        ws_frame.pop("request_id", None)

        assert ws_frame == sse_payload
