"""Sync + async singleflight coalescing.

When multiple callers issue the same logical request concurrently — same
method, path, body, tenant — only one upstream request fires. The other
callers block on the in-flight call's result. This is identical in
spirit to the Go ``golang.org/x/sync/singleflight`` package but with
separate sync and async surfaces so blocking primitives match the host
event loop.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any, Generic, TypeVar

__all__ = ["AsyncSingleflight", "Singleflight"]


T = TypeVar("T")


class _SyncCall(Generic[T]):
    """Per-key state shared by callers waiting on one upstream invocation."""

    __slots__ = ("event", "exc", "value")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.value: T | None = None
        self.exc: BaseException | None = None


class Singleflight:
    """Thread-safe singleflight gate (sync version)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, _SyncCall[Any]] = {}

    def call(self, key: str, fn: Callable[[], T]) -> T:
        """Run ``fn()`` if no other thread is already running it for ``key``.

        Concurrent calls with the same key block on the original until it
        finishes, then receive its result (or re-raise its exception).
        """
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                leader = False
                call: _SyncCall[T] = existing
            else:
                leader = True
                call = _SyncCall[T]()
                self._inflight[key] = call

        if leader:
            try:
                call.value = fn()
            except BaseException as exc:
                call.exc = exc
            finally:
                call.event.set()
                with self._lock:
                    self._inflight.pop(key, None)
        else:
            call.event.wait()

        if call.exc is not None:
            raise call.exc
        # ``leader`` guarantees value is set; cast for type-checker.
        return call.value  # type: ignore[return-value]


class _AsyncCall(Generic[T]):
    """Per-key state for the async singleflight gate."""

    __slots__ = ("future",)

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.future: asyncio.Future[T] = loop.create_future()


class AsyncSingleflight:
    """Async singleflight gate.

    Bound to a single event loop — the loop is captured lazily on first
    use. Calling ``call`` from a different loop raises ``RuntimeError``
    because asyncio futures are loop-scoped.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._inflight: dict[str, _AsyncCall[Any]] = {}

    async def call(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Run ``fn()`` once per ``key``; concurrent callers share the result."""
        loop = asyncio.get_running_loop()
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                fut: asyncio.Future[T] = existing.future
                return await fut
            call = _AsyncCall[T](loop)
            self._inflight[key] = call

        try:
            result = await fn()
        except BaseException as exc:
            call.future.set_exception(exc)
            async with self._lock:
                self._inflight.pop(key, None)
            # Suppress asyncio's "future exception was never retrieved"
            # warning. The leader is re-raising the exception itself; the
            # future is purely a fan-out channel for late followers.
            call.future.exception()
            raise
        else:
            call.future.set_result(result)
            async with self._lock:
                self._inflight.pop(key, None)
            return result
