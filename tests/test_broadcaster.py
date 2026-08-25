"""Broadcaster fan-out, driven directly rather than through HTTP.

Both regressions here are hangs -- the subscriber waits on a queue that never
receives a terminal message, so the SSE response never closes. Driving the
Broadcaster directly is what lets `asyncio.wait_for` turn "waits forever" into a
failure instead of a hung test run. `asyncio.run` rather than pytest-asyncio:
one less dev dependency, and each test owns a short-lived loop anyway.
"""

import asyncio

import pytest

import live
from live import Broadcaster

# Long enough that a bug can't be masked by the ticker racing us to publish.
WAIT = 2.0


def one_inning(gamePk: int) -> list[dict]:
    return [{"inning_num": 1}]


def twenty_innings(gamePk: int) -> list[dict]:
    return [{"inning_num": i} for i in range(20)]


async def drain_until_terminal(queue: asyncio.Queue) -> list[str]:
    """Read a subscriber's queue until a terminal message arrives, or fail."""
    seen: list[str] = []
    while True:
        message = await asyncio.wait_for(queue.get(), WAIT)
        seen.append(message["type"])
        if message["type"] in live.TERMINAL_TYPES:
            return seen


@pytest.fixture
def tiny_queue(monkeypatch):
    """Two slots, so a subscriber that never drains overflows immediately."""
    monkeypatch.setattr(live, "QUEUE_MAX", 2)


def test_subscriber_joining_after_a_ticker_finishes_still_gets_a_feed():
    """A finished ticker used to stay registered until the LAST subscriber left,
    so anyone joining in that window saw `subscribe` decline to start one and
    then waited forever."""

    async def scenario():
        broadcaster = Broadcaster(one_inning, interval=0)

        first = broadcaster.subscribe(777)
        assert await drain_until_terminal(first) == ["inning", "end"]

        # Deliberately do NOT unsubscribe `first` -- that window is the bug. Two
        # tabs on one game land here, as does StrictMode's double-mount in dev.
        second = broadcaster.subscribe(777)
        assert await drain_until_terminal(second) == ["inning", "end"]

    asyncio.run(scenario())


def test_slow_subscriber_is_dropped_with_a_terminal_failure(tiny_queue):
    """Evicting a backed-up client without telling it leaves its consumer on
    `queue.get()` forever and the response never closes."""

    async def scenario():
        broadcaster = Broadcaster(twenty_innings, interval=0)
        queue = broadcaster.subscribe(777)

        # Never drain it, so the queue fills and the ticker evicts us.
        await asyncio.sleep(0.2)
        assert broadcaster.subscriber_count(777) == 0

        assert (await drain_until_terminal(queue))[-1] == "failure"

    asyncio.run(scenario())


def test_dropped_subscriber_failure_carries_the_error_envelope(tiny_queue):
    """Same envelope as every other error, so errors.ts routes it through the
    same classify() as an HTTP failure."""

    async def scenario():
        broadcaster = Broadcaster(twenty_innings, interval=0)
        queue = broadcaster.subscribe(777)
        await asyncio.sleep(0.2)

        message = None
        while not queue.empty():
            message = queue.get_nowait()

        assert message is not None and message["type"] == "failure"
        error = message["error"]
        assert error["code"] == "DATA_SOURCE_UNAVAILABLE"
        assert error["details"]["gamePk"] == 777
        assert set(error) == {"code", "message", "details", "request_id"}

    asyncio.run(scenario())


def test_last_subscriber_out_cancels_the_ticker():
    """Otherwise an abandoned game replays to nobody until the process dies."""

    async def scenario():
        broadcaster = Broadcaster(one_inning, interval=10)
        queue = broadcaster.subscribe(777)
        ticker = broadcaster._tickers[777]

        broadcaster.unsubscribe(777, queue)

        with pytest.raises(asyncio.CancelledError):
            await ticker
        assert broadcaster.subscriber_count(777) == 0

    asyncio.run(scenario())


def test_two_subscribers_on_one_game_cost_one_read():
    """The fan-out claim itself -- one read no matter how many are watching.
    Driven directly rather than through two TestClients, which would each run
    the app in their own event loop and never wake each other's queues."""
    calls = []

    def counted(gamePk: int) -> list[dict]:
        calls.append(gamePk)
        return one_inning(gamePk)

    async def scenario():
        broadcaster = Broadcaster(counted, interval=0)
        first = broadcaster.subscribe(777)
        second = broadcaster.subscribe(777)

        assert broadcaster.subscriber_count(777) == 2
        # Both see the whole feed, not one each -- a fan-out, not a queue split.
        assert await drain_until_terminal(first) == ["inning", "end"]
        assert await drain_until_terminal(second) == ["inning", "end"]

        broadcaster.unsubscribe(777, first)
        broadcaster.unsubscribe(777, second)

    asyncio.run(scenario())
    assert calls == [777]
