"""Wire compatibility and cache mutation regressions for both clients."""

from __future__ import annotations

import asyncio
import gzip
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

import httpx
import pytest

from graphann import AsyncClient, Client
from graphann.errors import ServerError

URL = "http://test.invalid"
RESOURCE_ID = "folder/a b%?#é"
RESOURCE_PATH = b"/v1/tenants/t/indexes/i/resources/folder%2Fa%20b%25%3F%23%C3%A9"


class CompressionOptions(TypedDict, total=False):
    gzip_threshold: int


@pytest.mark.parametrize("compressed", [False, True])
def test_sync_large_resource_request(compressed: bool) -> None:
    text = "large document " * 10000

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == RESOURCE_PATH
        assert request.headers.get("Content-Encoding") == (
            "gzip" if compressed else None
        )
        body = gzip.decompress(request.content) if compressed else request.content
        assert json.loads(body)["text"] == text
        return httpx.Response(
            200,
            json={
                "resource_id": RESOURCE_ID,
                "operation": "create",
                "chunks_added": 1,
                "chunks_tombstoned": 0,
            },
        )

    options: CompressionOptions = {"gzip_threshold": 64 * 1024} if compressed else {}
    with Client(
        base_url=URL, transport=httpx.MockTransport(respond), **options
    ) as client:
        assert (
            client.upsert_resource("t", "i", RESOURCE_ID, text).resource_id
            == RESOURCE_ID
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("compressed", [False, True])
async def test_async_large_resource_request(compressed: bool) -> None:
    text = "large document " * 10000

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == RESOURCE_PATH
        assert request.headers.get("Content-Encoding") == (
            "gzip" if compressed else None
        )
        body = gzip.decompress(request.content) if compressed else request.content
        assert json.loads(body)["text"] == text
        return httpx.Response(
            200,
            json={
                "resource_id": RESOURCE_ID,
                "operation": "create",
                "chunks_added": 1,
                "chunks_tombstoned": 0,
            },
        )

    options: CompressionOptions = {"gzip_threshold": 64 * 1024} if compressed else {}
    async with AsyncClient(
        base_url=URL, transport=httpx.MockTransport(respond), **options
    ) as client:
        result = await client.upsert_resource("t", "i", RESOURCE_ID, text)
        assert result.resource_id == RESOURCE_ID


@pytest.mark.parametrize(
    "mutation",
    [
        "create_api_key",
        "revoke_api_key",
        "run_index_gc",
        "compact_index",
        "clear_pending",
    ],
)
def test_sync_mutations_invalidate_cached_reads(mutation: str) -> None:
    changed = False

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal changed
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "tenants": [{"id": "new" if changed else "old", "name": "tenant"}]
                },
            )
        changed = True
        return httpx.Response(200, json={"id": "key", "deleted_count": 1})

    with Client(
        base_url=URL, cache_ttl=60, transport=httpx.MockTransport(respond)
    ) as client:
        assert client.list_tenants()[0].id == "old"
        if mutation == "create_api_key":
            client.create_api_key("t", name="key")
        elif mutation == "revoke_api_key":
            client.revoke_api_key("t", "key")
        else:
            getattr(client, mutation)("t", "i")
        assert client.list_tenants()[0].id == "new"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "create_api_key",
        "revoke_api_key",
        "run_index_gc",
        "compact_index",
        "clear_pending",
    ],
)
async def test_async_mutations_invalidate_cached_reads(mutation: str) -> None:
    changed = False

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal changed
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "tenants": [{"id": "new" if changed else "old", "name": "tenant"}]
                },
            )
        changed = True
        return httpx.Response(200, json={"id": "key", "deleted_count": 1})

    async with AsyncClient(
        base_url=URL, cache_ttl=60, transport=httpx.MockTransport(respond)
    ) as client:
        assert (await client.list_tenants())[0].id == "old"
        if mutation == "create_api_key":
            await client.create_api_key("t", name="key")
        elif mutation == "revoke_api_key":
            await client.revoke_api_key("t", "key")
        else:
            await getattr(client, mutation)("t", "i")
        assert (await client.list_tenants())[0].id == "new"


@pytest.mark.parametrize("new_read_first", [False, True])
def test_sync_mutation_separates_inflight_reads(new_read_first: bool) -> None:
    started = threading.Event()
    release = threading.Event()
    changed = False
    searches = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal changed, searches
        if request.url.path.endswith("/search"):
            searches += 1
            value = "new" if changed else "old"
            if value == "old":
                started.set()
                assert release.wait(5)
            return httpx.Response(200, json={"results": [{"id": value}], "total": 1})
        changed = True
        return httpx.Response(200, json={"deleted_count": 1})

    with Client(
        base_url=URL, cache_ttl=60, transport=httpx.MockTransport(respond)
    ) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(client.search, "t", "i", query="q")
            try:
                assert started.wait(5)
                client.run_index_gc("t", "i")
                if new_read_first:
                    fresh = pool.submit(client.search, "t", "i", query="q")
                    assert fresh.result(timeout=2)[0].id == "new"
            finally:
                release.set()
            assert old.result(timeout=2)[0].id == "old"
        assert client.search("t", "i", query="q")[0].id == "new"
        assert client.search("t", "i", query="q")[0].id == "new"
        assert searches == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("new_read_first", [False, True])
async def test_async_mutation_separates_inflight_reads(new_read_first: bool) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    changed = False
    searches = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal changed, searches
        if request.url.path.endswith("/search"):
            searches += 1
            value = "new" if changed else "old"
            if value == "old":
                started.set()
                await asyncio.wait_for(release.wait(), 5)
            return httpx.Response(200, json={"results": [{"id": value}], "total": 1})
        changed = True
        return httpx.Response(200, json={"deleted_count": 1})

    async with AsyncClient(
        base_url=URL, cache_ttl=60, transport=httpx.MockTransport(respond)
    ) as client:
        old = asyncio.create_task(client.search("t", "i", query="q"))
        try:
            await asyncio.wait_for(started.wait(), 5)
            await client.run_index_gc("t", "i")
            if new_read_first:
                fresh = await asyncio.wait_for(client.search("t", "i", query="q"), 2)
                assert fresh[0].id == "new"
        finally:
            release.set()
            previous = await old
        assert previous[0].id == "old"
        assert (await client.search("t", "i", query="q"))[0].id == "new"
        assert (await client.search("t", "i", query="q"))[0].id == "new"
        assert searches == 2


def test_sync_read_only_posts_and_failed_mutations_keep_cache() -> None:
    reads = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        if request.method == "GET":
            reads += 1
            return httpx.Response(
                200, json={"tenants": [{"id": "t", "name": "tenant"}]}
            )
        if request.url.path.endswith("/gc"):
            return httpx.Response(500, json={"error": "failed"})
        return httpx.Response(200, json={"results": [], "total": 0})

    with Client(
        base_url=URL,
        cache_ttl=60,
        max_retries=0,
        transport=httpx.MockTransport(respond),
    ) as client:
        client.list_tenants()
        client.search("t", "i", query="q", cache=False)
        client.batch_search("t", "i", [{"query": "q"}])
        client.multi_search("org", "user", "q", cache=False)
        with pytest.raises(ServerError):
            client.run_index_gc("t", "i")
        assert client.list_tenants()[0].id == "t"
        assert reads == 1


@pytest.mark.asyncio
async def test_async_read_only_posts_and_failed_mutations_keep_cache() -> None:
    reads = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        if request.method == "GET":
            reads += 1
            return httpx.Response(
                200, json={"tenants": [{"id": "t", "name": "tenant"}]}
            )
        if request.url.path.endswith("/gc"):
            return httpx.Response(500, json={"error": "failed"})
        return httpx.Response(200, json={"results": [], "total": 0})

    async with AsyncClient(
        base_url=URL,
        cache_ttl=60,
        max_retries=0,
        transport=httpx.MockTransport(respond),
    ) as client:
        await client.list_tenants()
        await client.search("t", "i", query="q", cache=False)
        await client.batch_search("t", "i", [{"query": "q"}])
        await client.multi_search("org", "user", "q", cache=False)
        with pytest.raises(ServerError):
            await client.run_index_gc("t", "i")
        assert (await client.list_tenants())[0].id == "t"
        assert reads == 1
