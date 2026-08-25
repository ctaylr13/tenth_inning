"""The replay ticker and its subscriber fan-out.

One ticker per gamePk, shared by everyone watching it, so the database is read
once per game rather than once per client -- the whole efficiency argument over
polling. The registry is `dict[int, set[Queue]]`; at one instance that IS the
fan-out, and a bus replaces the registry once a second process exists. Knows
nothing about HTTP or duckdb, so the same ticker serves SSE and websockets.

Every subscriber gets exactly one terminal message -- `end` or `failure`.
Consumers block waiting for one, so a path that drops a subscriber without
sending one leaves its stream open forever.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from typing import Any

from errors import FAILURE_TYPE, ErrorCode, failure_frame

logger = logging.getLogger("tenth_inning")

InningLoader = Callable[[int], list[dict[str, Any]]]

# A subscriber this far behind won't catch up, and an unbounded queue is an OOM.
QUEUE_MAX = 32

DEFAULT_INTERVAL_SECONDS = 1.0

# `failure` comes from errors.py so the frame vocabulary has one owner.
END_TYPE = "end"
TERMINAL_TYPES = (END_TYPE, FAILURE_TYPE)


def _failure(gamePk: int, message: str) -> dict[str, Any]:
    """The ticker's one failure mode, as a terminal frame. `gamePk` alongside
    the envelope so a client watching two games can tell them apart."""
    return {
        "gamePk": gamePk,
        **failure_frame(
            ErrorCode.DATA_SOURCE_UNAVAILABLE,
            message,
            uuid.uuid4().hex[:12],
            {"gamePk": gamePk},
        ),
    }


class Broadcaster:
    """Fan-out for replayed game feeds. One ticker task per gamePk."""

    def __init__(
        self,
        load_innings: InningLoader,
        interval: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._load = load_innings
        # Public so tests can drop it to ~0 instead of sleeping in real time.
        self.interval = interval
        self._subscribers: dict[int, set[asyncio.Queue]] = {}
        self._tickers: dict[int, asyncio.Task] = {}

    # subscription
    def subscribe(self, gamePk: int) -> asyncio.Queue:
        """Join a game's feed, starting its ticker if nobody else is watching."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self._subscribers.setdefault(gamePk, set()).add(queue)

        # `done()` as well as absence: a ticker that finished or was cancelled
        # would otherwise leave this subscriber waiting on one that never
        # publishes again.
        ticker = self._tickers.get(gamePk)
        if ticker is None or ticker.done():
            self._tickers[gamePk] = asyncio.create_task(self._run(gamePk))
        return queue

    def unsubscribe(self, gamePk: int, queue: asyncio.Queue) -> None:
        """Leave. The last one out stops the ticker -- otherwise a finished game
        replays to nobody until the process dies."""
        subscribers = self._subscribers.get(gamePk)
        if subscribers is None:
            return

        subscribers.discard(queue)
        if subscribers:
            return

        self._subscribers.pop(gamePk, None)
        ticker = self._tickers.pop(gamePk, None)
        if ticker is not None:
            ticker.cancel()

    def subscriber_count(self, gamePk: int) -> int:
        return len(self._subscribers.get(gamePk, ()))

    # fan-out
    def _publish(self, gamePk: int, message: dict[str, Any]) -> None:
        """The fan-out -- one registry, one loop."""
        for queue in list(self._subscribers.get(gamePk, ())):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Dropping the slow client is the only option that doesn't
                # punish the ones keeping up.
                logger.warning(
                    "dropping subscriber that fell behind [gamePk=%s]", gamePk
                )
                self._drop(gamePk, queue)

    def _drop(self, gamePk: int, queue: asyncio.Queue) -> None:
        """Evict a subscriber that stopped draining, terminal frame first. Its
        queue is full, so clear the stale backlog to make room -- without the
        frame the consumer blocks on `get()` forever."""
        while not queue.empty():
            queue.get_nowait()

        queue.put_nowait(
            _failure(gamePk, "The live feed fell too far behind and was closed.")
        )
        self.unsubscribe(gamePk, queue)

    # the ticker
    async def _run(self, gamePk: int) -> None:
        """Read the game once, then release one inning per interval. Never
        raises: a ticker that dies takes its task down silently and subscribers
        just stop hearing anything, so failures go out as a message instead."""
        try:
            try:
                # Synchronous duckdb, so off-thread -- one slow query must not
                # stall every other connection on the event loop.
                innings = await asyncio.to_thread(self._load, gamePk)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("replay ticker failed to load [gamePk=%s]", gamePk)
                self._publish(
                    gamePk,
                    _failure(
                        gamePk,
                        "The data source is temporarily unavailable. Try again shortly.",
                    ),
                )
                return

            for seq, inning in enumerate(innings, start=1):
                await asyncio.sleep(self.interval)
                self._publish(
                    gamePk,
                    {"type": "inning", "gamePk": gamePk, "seq": seq, "inning": inning},
                )

            # Zero innings is an empty state, not a failure.
            self._publish(
                gamePk, {"type": END_TYPE, "gamePk": gamePk, "innings": len(innings)}
            )
        finally:
            # Deregister, or the next subscriber sees a live entry, starts no
            # ticker, and hangs.
            if self._tickers.get(gamePk) is asyncio.current_task():
                self._tickers.pop(gamePk, None)
