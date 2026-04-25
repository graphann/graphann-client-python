"""Singleflight tests (sync and async)."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from graphann._singleflight import AsyncSingleflight, Singleflight


def test_sync_coalesces_concurrent_calls() -> None:
    sf = Singleflight()
    counter = {"n": 0}
    release = threading.Event()
    leader_started = threading.Event()

    def slow() -> int:
        # Signal that the leader is now executing, then block until the
        # main test thread has released the followers. By the time
        # ``release.set()`` is called, all five threads have already
        # entered ``sf.call`` and four of them are parked on
        # ``call.event``.
        leader_started.set()
        release.wait()
        counter["n"] += 1
        return 42

    threads: list[threading.Thread] = []
    results: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        v = sf.call("k", slow)
        with lock:
            results.append(v)

    for _ in range(5):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    # Wait for the leader thread to enter ``slow``; gives the followers
    # plenty of scheduling time to queue behind it.
    assert leader_started.wait(timeout=2.0), "leader never entered slow()"
    time.sleep(0.05)  # allow followers to park on the event
    release.set()
    for t in threads:
        t.join()

    assert results == [42, 42, 42, 42, 42]
    # One leader, four followers — only one execution.
    assert counter["n"] == 1


def test_sync_propagates_exception_to_followers() -> None:
    sf = Singleflight()

    def explode() -> int:
        raise RuntimeError("boom")

    threads: list[threading.Thread] = []
    excs: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            sf.call("k", explode)
        except BaseException as exc:
            with lock:
                excs.append(exc)

    for _ in range(3):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    assert len(excs) == 3
    assert all(isinstance(e, RuntimeError) and str(e) == "boom" for e in excs)


def test_sync_subsequent_call_runs_again() -> None:
    """After the first call returns, a fresh call must trigger a new run."""
    sf = Singleflight()
    n = {"v": 0}

    def go() -> int:
        n["v"] += 1
        return n["v"]

    assert sf.call("k", go) == 1
    assert sf.call("k", go) == 2
    assert n["v"] == 2


@pytest.mark.asyncio
async def test_async_coalesces() -> None:
    sf = AsyncSingleflight()
    counter = {"n": 0}

    async def slow() -> int:
        await asyncio.sleep(0.01)
        counter["n"] += 1
        return 7

    results = await asyncio.gather(
        sf.call("k", slow),
        sf.call("k", slow),
        sf.call("k", slow),
    )
    assert results == [7, 7, 7]
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_async_distinct_keys_run_independently() -> None:
    sf = AsyncSingleflight()
    counter = {"n": 0}

    async def go() -> int:
        await asyncio.sleep(0.01)
        counter["n"] += 1
        return counter["n"]

    a, b = await asyncio.gather(sf.call("k1", go), sf.call("k2", go))
    assert {a, b} == {1, 2}
    assert counter["n"] == 2


@pytest.mark.asyncio
async def test_async_propagates_exception() -> None:
    sf = AsyncSingleflight()

    async def explode() -> int:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await asyncio.gather(
            sf.call("k", explode),
            sf.call("k", explode),
        )
