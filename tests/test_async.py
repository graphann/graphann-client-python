"""Asynchronous AsyncClient tests using ``respx``."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from graphann import AsyncClient
from graphann.errors import AuthenticationError, NotFoundError, RateLimitError

URL = "http://test.invalid"


def make_client(**kwargs: object) -> AsyncClient:
    return AsyncClient(
        base_url=URL,
        api_key="key",
        tenant_id="t_unit",
        max_retries=0,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_health() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{URL}/health").mock(return_value=httpx.Response(200, json={"status": "healthy"}))
        async with make_client() as c:
            h = await c.health()
    assert h.status == "healthy"


@pytest.mark.asyncio
async def test_search_text_round_trip() -> None:
    payload = {
        "results": [{"id": "c1", "score": 0.5}, {"id": "c2", "score": 0.4}],
        "total": 2,
    }
    with respx.mock() as mock:
        route = mock.post(f"{URL}/v1/tenants/t_unit/indexes/i_1/search/text").mock(
            return_value=httpx.Response(200, json=payload)
        )
        async with make_client() as c:
            results = await c.search_text("t_unit", "i_1", "hello")
    assert [r.id for r in results] == ["c1", "c2"]
    body = route.calls.last.request.content
    import json

    assert json.loads(body) == {"query": "hello", "k": 10}


@pytest.mark.asyncio
async def test_async_pagination() -> None:
    """``list_documents`` returns an async iterator that follows cursors."""
    page1 = {
        "documents": [
            {"id": "a", "text": "alpha"},
            {"id": "b", "text": "beta"},
        ],
        "next_cursor": "tok-1",
    }
    page2 = {"documents": [{"id": "c", "text": "gamma"}]}

    with respx.mock() as mock:
        route = mock.get(f"{URL}/v1/tenants/t_unit/indexes/i_1/documents").mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        async with make_client() as c:
            collected: list[str] = []
            async for page in c.list_documents("t_unit", "i_1", page_size=2):
                collected.extend(d.id for d in page.items)
    assert collected == ["a", "b", "c"]
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_async_singleflight() -> None:
    """Concurrent identical search calls collapse to one upstream request.

    A real upstream takes non-zero time. We simulate that with a
    side-effect that blocks on an event, ensuring all three coroutines
    arrive at the singleflight gate before any of them finish.
    """
    gate = asyncio.Event()
    upstream_calls = 0

    async def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        await gate.wait()
        return httpx.Response(200, json={"results": [], "total": 0})

    with respx.mock() as mock:
        mock.post(f"{URL}/v1/tenants/t_unit/indexes/i_1/search/text").mock(side_effect=respond)

        async with make_client() as c:
            tasks = [asyncio.create_task(c.search_text("t_unit", "i_1", "hello")) for _ in range(3)]
            # Yield control so all three tasks run their request setup
            # and reach the singleflight gate.
            await asyncio.sleep(0.05)
            gate.set()
            results = await asyncio.gather(*tasks)

    assert all(r == [] for r in results)
    # Singleflight collapses concurrent identical calls into one.
    assert upstream_calls == 1


@pytest.mark.asyncio
async def test_async_error_mapping() -> None:
    with respx.mock() as mock:
        mock.get(f"{URL}/v1/tenants/t_unknown").mock(
            return_value=httpx.Response(
                404,
                json={"error": {"code": "not_found", "message": "Tenant not found"}},
            )
        )
        async with make_client() as c:
            with pytest.raises(NotFoundError) as exc_info:
                await c.get_tenant("t_unknown")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


@pytest.mark.asyncio
async def test_async_rate_limit_carries_retry_after() -> None:
    with respx.mock() as mock:
        mock.get(f"{URL}/v1/tenants").mock(
            return_value=httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={"error": {"code": "rate_limited", "message": "slow"}},
            )
        )
        async with make_client() as c:
            with pytest.raises(RateLimitError) as exc_info:
                await c.list_tenants()
    assert exc_info.value.retry_after == 3.0


@pytest.mark.asyncio
async def test_async_auth_error() -> None:
    with respx.mock() as mock:
        mock.get(f"{URL}/v1/tenants").mock(
            return_value=httpx.Response(
                401, json={"error": {"code": "unauthorized", "message": "bad key"}}
            )
        )
        async with make_client() as c:
            with pytest.raises(AuthenticationError):
                await c.list_tenants()


@pytest.mark.asyncio
async def test_async_create_index_round_trip() -> None:
    with respx.mock() as mock:
        mock.post(f"{URL}/v1/tenants/t_unit/indexes").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": "i_1",
                    "tenant_id": "t_unit",
                    "name": "demo",
                    "status": "empty",
                    "num_docs": 0,
                    "num_chunks": 0,
                    "dimension": 0,
                    "created_at": "2026-04-25T00:00:00Z",
                    "updated_at": "2026-04-25T00:00:00Z",
                },
            )
        )
        async with make_client() as c:
            idx = await c.create_index("t_unit", "demo")
    assert idx.id == "i_1"
    assert idx.status == "empty"
