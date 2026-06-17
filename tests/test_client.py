"""Synchronous Client unit tests using ``pytest-httpx``."""

from __future__ import annotations

import gzip
import json

import pytest
from pytest_httpx import HTTPXMock

from graphann import Client
from graphann.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    GraphANNError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ValidationError,
)


@pytest.fixture
def url() -> str:
    return "http://test.invalid"


def make_client(url: str, **kwargs: object) -> Client:
    return Client(
        base_url=url,
        api_key="key",
        tenant_id="t_unit",
        max_retries=0,
        **kwargs,  # type: ignore[arg-type]
    )


def test_health_returns_parsed_model(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/health",
        method="GET",
        json={"status": "healthy"},
    )
    with make_client(url) as c:
        h = c.health()
    assert h.status == "healthy"


def test_create_tenant_posts_body_and_parses_response(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="POST",
        json={"id": "t_123", "name": "demo", "created_at": "2026-04-25T00:00:00Z"},
        status_code=201,
    )
    with make_client(url) as c:
        t = c.create_tenant("demo")
    assert t.id == "t_123"
    assert t.name == "demo"
    assert t.created_at is not None

    request = httpx_mock.get_request()
    assert request is not None
    body = json.loads(request.content)
    assert body == {"name": "demo"}
    # Auth + tenant headers
    assert request.headers["X-API-Key"] == "key"
    assert request.headers["Authorization"] == "Bearer key"
    assert request.headers["X-Tenant-ID"] == "t_unit"
    assert "graphann-python/" in request.headers["User-Agent"]


def test_list_tenants(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        json={
            "tenants": [
                {"id": "t_1", "name": "one", "index_count": 2},
                {"id": "t_2", "name": "two"},
            ],
            "total": 2,
        },
    )
    with make_client(url) as c:
        tenants = c.list_tenants()
    assert [t.id for t in tenants] == ["t_1", "t_2"]
    assert tenants[0].index_count == 2


def test_search_sends_correct_body(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/search",
        method="POST",
        json={
            "results": [
                {"id": "c1", "score": 0.9, "text": "hi", "metadata": {"k": "v"}},
                {"id": "c2", "score": 0.8},
            ],
            "total": 2,
        },
    )
    with make_client(url) as c:
        results = c.search("t_unit", "i_1", query="hello world", k=5)
    assert len(results) == 2
    assert results[0].id == "c1"
    assert results[0].score == 0.9

    request = httpx_mock.get_request()
    assert request is not None
    body = json.loads(request.content)
    assert body == {"query": "hello world", "k": 5}


def test_upsert_resource_create(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/resources/res_1",
        method="PUT",
        json={
            "resource_id": "res_1",
            "chunks_added": 3,
            "chunks_tombstoned": 0,
            "operation": "create",
        },
    )
    with make_client(url) as c:
        resp = c.upsert_resource("t_unit", "i_1", "res_1", "hello world")
    assert resp.resource_id == "res_1"
    assert resp.operation == "create"
    assert resp.chunks_added == 3
    assert resp.chunks_tombstoned == 0


def test_upsert_resource_update(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/resources/res_1",
        method="PUT",
        json={
            "resource_id": "res_1",
            "chunks_added": 2,
            "chunks_tombstoned": 3,
            "operation": "update",
        },
    )
    with make_client(url) as c:
        resp = c.upsert_resource(
            "t_unit", "i_1", "res_1", "updated text", metadata={"source": "api"}
        )
    assert resp.operation == "update"
    assert resp.chunks_tombstoned == 3
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body["metadata"] == {"source": "api"}


def test_compact_index_409_raises_conflict(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/compact",
        method="POST",
        status_code=409,
        json={
            "error": {
                "code": "compact_in_progress",
                "message": "Compaction already running",
            }
        },
    )
    with make_client(url) as c, pytest.raises(ConflictError) as exc_info:
        c.compact_index("t_unit", "i_1")
    assert exc_info.value.status_code == 409


def test_create_index_with_compression_and_approximate(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes",
        method="POST",
        status_code=201,
        json={
            "id": "i_new",
            "tenant_id": "t_unit",
            "name": "pq-index",
            "status": "empty",
            "compression": "pq",
            "approximate": True,
        },
    )
    with make_client(url) as c:
        idx = c.create_index("t_unit", "pq-index", compression="pq", approximate=True)
    assert idx.compression == "pq"
    assert idx.approximate is True
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body["compression"] == "pq"
    assert body["approximate"] is True


def test_search_filter_equals(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/search",
        method="POST",
        json={"results": [], "total": 0},
    )
    from graphann.models import SearchFilter

    with make_client(url) as c:
        c.search(
            "t_unit",
            "i_1",
            query="test",
            filter=SearchFilter(equals={"env": "prod"}),
        )
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body["filter"] == {"equals": {"env": "prod"}}


def test_add_documents_validates_input(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/documents",
        method="POST",
        status_code=201,
        json={"added": 2, "index_id": "i_1", "chunk_ids": ["chunk-0", "chunk-1"]},
    )
    with make_client(url) as c:
        resp = c.add_documents(
            "t_unit",
            "i_1",
            [
                {"id": "a", "text": "alpha"},
                {"id": "b", "text": "beta", "metadata": {"k": "v"}},
            ],
        )
    assert resp.added == 2
    assert resp.chunk_ids == ["chunk-0", "chunk-1"]


def test_delete_index_returns_none(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1",
        method="DELETE",
        status_code=204,
    )
    with make_client(url) as c:
        c.delete_index("t_unit", "i_1")


def test_search_requires_query_or_vector(url: str) -> None:
    with make_client(url) as c, pytest.raises(ValueError, match="query or vector"):
        c.search("t_unit", "i_1")


@pytest.mark.parametrize(
    ("status", "exc_cls", "code"),
    [
        (401, AuthenticationError, "unauthorized"),
        (403, AuthorizationError, "forbidden"),
        (404, NotFoundError, "not_found"),
        (409, ConflictError, "conflict"),
        (413, PayloadTooLargeError, "payload_too_large"),
        (429, RateLimitError, "rate_limited"),
        (500, ServerError, "internal_error"),
        (503, ServerError, "service_unavailable"),
    ],
)
def test_error_mapping(
    httpx_mock: HTTPXMock,
    url: str,
    status: int,
    exc_cls: type[GraphANNError],
    code: str,
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="POST",
        status_code=status,
        json={"error": {"code": code, "message": "boom"}},
    )
    with make_client(url) as c, pytest.raises(exc_cls) as exc_info:
        c.create_tenant("demo")
    assert exc_info.value.status_code == status
    assert exc_info.value.code == code
    assert "boom" in str(exc_info.value)


def test_rate_limit_extracts_retry_after(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="POST",
        status_code=429,
        json={"error": {"code": "rate_limited", "message": "slow down"}},
        headers={"Retry-After": "7"},
    )
    with make_client(url) as c, pytest.raises(RateLimitError) as exc_info:
        c.create_tenant("demo")
    assert exc_info.value.retry_after == 7.0


def test_validation_error_on_bad_response(httpx_mock: HTTPXMock, url: str) -> None:
    # Server returns wrong shape for ``Health`` (status missing entirely).
    httpx_mock.add_response(
        url=f"{url}/health",
        method="GET",
        json={"unrelated": "fields"},
    )
    with make_client(url) as c, pytest.raises(ValidationError) as exc_info:
        c.health()
    assert "did not match" in str(exc_info.value)
    assert exc_info.value.pydantic_error is not None


def test_large_body_is_gzipped(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/import",
        method="POST",
        status_code=201,
        json={"imported": 1, "index_id": "i_1", "document_ids": [0]},
    )
    big_text = "x" * (128 * 1024)  # 128 KiB
    with make_client(url, gzip_threshold=64 * 1024) as c:
        c.import_documents("t_unit", "i_1", [{"id": "huge", "text": big_text}])

    req = httpx_mock.get_request()
    assert req is not None
    assert req.headers.get("Content-Encoding") == "gzip"
    body = gzip.decompress(req.content)
    parsed = json.loads(body)
    assert parsed["documents"][0]["text"] == big_text


def test_response_cache_avoids_duplicate_requests(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        json={"tenants": [{"id": "t_1", "name": "n"}], "total": 1},
    )
    with make_client(url, cache_ttl=10.0) as c:
        first = c.list_tenants()
        second = c.list_tenants()
    assert [t.id for t in first] == [t.id for t in second]
    # Only one request observed even though list_tenants was called twice.
    assert len(httpx_mock.get_requests()) == 1


def test_cache_invalidated_on_write(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        json={"tenants": [{"id": "t_1", "name": "n"}], "total": 1},
    )
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="POST",
        status_code=201,
        json={"id": "t_2", "name": "fresh"},
    )
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        json={
            "tenants": [{"id": "t_1", "name": "n"}, {"id": "t_2", "name": "fresh"}],
            "total": 2,
        },
    )
    with make_client(url, cache_ttl=10.0) as c:
        before = c.list_tenants()
        c.create_tenant("fresh")
        after = c.list_tenants()
    assert len(before) == 1
    assert len(after) == 2  # post-write cache miss → second GET fired


def test_cluster_health(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/cluster/health",
        method="GET",
        json={
            "status": "ok",
            "cluster_size": 3,
            "alive_nodes": 3,
            "raft_has_leader": True,
            "under_replicated_shards": 0,
        },
    )
    with make_client(url) as c:
        h = c.get_cluster_health()
    assert h.status == "ok"
    assert h.alive_nodes == 3
    assert h.raft_has_leader is True


def test_hot_model_switch_returns_job(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/embedding-model",
        method="PATCH",
        status_code=202,
        json={"job_id": "job_abc", "status": "queued"},
    )
    with make_client(url) as c:
        resp = c.switch_embedding_model(
            "t_unit",
            "i_1",
            embedding_backend="ollama",
            model="nomic-embed-text",
            dimension=768,
        )
    assert resp.job_id == "job_abc"
    assert resp.status == "queued"


def test_get_job_returns_typed_model(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/jobs/job_abc",
        method="GET",
        json={
            "job_id": "job_abc",
            "kind": "reembed",
            "status": "running",
            "progress": {"chunks_done": 100, "chunks_total": 1000},
            "created_at": "2026-04-25T00:00:00Z",
        },
    )
    with make_client(url) as c:
        job = c.get_job("job_abc")
    assert job.job_id == "job_abc"
    assert job.kind == "reembed"
    assert job.progress is not None
    assert job.progress.chunks_done == 100


def test_metrics_hook_invoked(httpx_mock: HTTPXMock, url: str) -> None:
    captured: list[tuple[str, float, dict[str, str]]] = []

    def hook(name: str, value: float, labels):  # type: ignore[no-untyped-def]
        captured.append((name, value, dict(labels)))

    httpx_mock.add_response(
        url=f"{url}/health",
        method="GET",
        json={"status": "healthy"},
    )
    with make_client(url, metrics_hook=hook) as c:
        c.health()
    assert any(
        name == "graphann.http.request_duration_seconds" for name, _, _ in captured
    )


def test_search_filter_passthrough(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/search",
        method="POST",
        json={"results": [], "total": 0},
    )
    with make_client(url) as c:
        c.search(
            "t_unit",
            "i_1",
            query="hello",
            k=3,
            filter={"repo_ids": ["r1", "r2"], "exclude_external_ids": ["x"]},
        )
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body["filter"] == {"repo_ids": ["r1", "r2"], "exclude_external_ids": ["x"]}


def test_user_agent_carries_version(httpx_mock: HTTPXMock, url: str) -> None:
    from graphann import __version__

    httpx_mock.add_response(
        url=f"{url}/health",
        method="GET",
        json={"status": "healthy"},
    )
    with make_client(url) as c:
        c.health()
    req = httpx_mock.get_request()
    assert req is not None
    assert __version__ in req.headers["User-Agent"]


def test_get_chunk_returns_typed_model(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/chunks/42",
        method="GET",
        json={
            "chunk_id": 42,
            "text": "the quick brown fox",
            "document_id": 7,
            "chunk_index": 2,
            "start": 64,
            "end": 84,
        },
    )
    with make_client(url) as c:
        chunk = c.get_chunk("t_unit", "i_1", 42)
    assert chunk.chunk_id == 42
    assert chunk.text == "the quick brown fox"
    assert chunk.document_id == 7
    assert chunk.start == 64
    assert chunk.end == 84


def test_delete_chunks_sends_id_list_to_placeholder_path(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/chunks/0",
        method="DELETE",
        json={"deleted": 3, "index_id": "i_1"},
    )
    with make_client(url) as c:
        resp = c.delete_chunks("t_unit", "i_1", [10, 11, 12])
    assert resp.deleted == 3
    assert resp.index_id == "i_1"
    req = httpx_mock.get_request()
    assert req is not None
    assert json.loads(req.content) == {"chunk_ids": [10, 11, 12]}


def test_delete_chunks_rejects_empty_list(url: str) -> None:
    with make_client(url) as c, pytest.raises(
        ValueError, match="at least one chunk id"
    ):
        c.delete_chunks("t_unit", "i_1", [])


def test_get_llm_settings_uses_canonical_path(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/orgs/org_1/llm-settings",
        method="GET",
        json={
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "***abcd",
            "temperature": 0.2,
            "max_tokens": 1024,
        },
    )
    with make_client(url) as c:
        s = c.get_llm_settings("org_1")
    assert s.provider == "openai"
    assert s.api_key == "***abcd"


def test_update_llm_settings_uses_patch_and_returns_raw_settings(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/orgs/org_1/llm-settings",
        method="PATCH",
        json={
            "provider": "anthropic",
            "model": "claude-opus-4",
            "api_key": "***wxyz",
            "temperature": 0.1,
            "max_tokens": 2048,
        },
    )
    with make_client(url) as c:
        merged = c.update_llm_settings(
            "org_1",
            {"provider": "anthropic", "model": "claude-opus-4"},
        )
    assert merged.provider == "anthropic"
    assert merged.model == "claude-opus-4"
    req = httpx_mock.get_request()
    assert req is not None
    assert req.method == "PATCH"
    assert json.loads(req.content) == {
        "provider": "anthropic",
        "model": "claude-opus-4",
    }


def test_delete_llm_settings_uses_canonical_path(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/orgs/org_1/llm-settings",
        method="DELETE",
        json={"provider": "ollama", "model": "llama3.2:3b"},
    )
    with make_client(url) as c:
        resp = c.delete_llm_settings("org_1")
    assert resp == {"provider": "ollama", "model": "llama3.2:3b"}


def test_cleanup_orphans_default(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/admin/cleanup-orphans",
        method="POST",
        json={
            "removed": ["/data/tenants/t/indexes/i.compact"],
            "freed_bytes": 4096,
            "min_age": "1h0m0s",
            "dry_run": False,
        },
    )
    with make_client(url) as c:
        resp = c.cleanup_orphans()
    assert resp.freed_bytes == 4096
    assert resp.removed == ["/data/tenants/t/indexes/i.compact"]
    assert resp.min_age == "1h0m0s"
    assert resp.dry_run is False
    # No params sent on the default call.
    sent = httpx_mock.get_request()
    assert sent is not None
    assert sent.url.params.get("min_age") is None
    assert sent.url.params.get("dry_run") is None


def test_add_documents_with_precomputed_vectors(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/documents",
        method="POST",
        status_code=201,
        json={"added": 2, "index_id": "i_1", "chunk_ids": ["c-0", "c-1"]},
    )
    with make_client(url) as c:
        resp = c.add_documents(
            "t_unit",
            "i_1",
            [
                {"id": "a", "text": "alpha", "vector": [0.1, 0.2]},
                {"id": "b", "text": "beta", "vector": [0.3, 0.4]},
            ],
        )
    assert resp.added == 2
    assert resp.external_ids is None  # server did not mint any
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body["documents"][0]["vector"] == [0.1, 0.2]
    assert body["documents"][1]["vector"] == [0.3, 0.4]
    # No bulk-load flags unless explicitly requested.
    assert "defer_save" not in body
    assert "bulk" not in body


def test_add_documents_passes_defer_save_and_bulk(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/documents",
        method="POST",
        status_code=201,
        json={"added": 1, "index_id": "i_1", "chunk_ids": ["c-0"]},
    )
    with make_client(url) as c:
        c.add_documents(
            "t_unit",
            "i_1",
            [{"id": "a", "text": "alpha"}],
            defer_save=True,
            bulk=True,
        )
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body["defer_save"] is True
    assert body["bulk"] is True


def test_add_documents_parses_minted_external_ids(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/documents",
        method="POST",
        status_code=201,
        json={
            "added": 2,
            "index_id": "i_1",
            "chunk_ids": ["c-0", "c-1"],
            "external_ids": ["minted-1", "client-supplied"],
        },
    )
    with make_client(url) as c:
        resp = c.add_documents(
            "t_unit",
            "i_1",
            [{"text": "no id"}, {"id": "client-supplied", "text": "has id"}],
        )
    # Positionally aligned with the request array.
    assert resp.external_ids == ["minted-1", "client-supplied"]


def test_flush_index_sends_json_content_type(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/flush",
        method="POST",
        json={"flushed": True},
    )
    with make_client(url) as c:
        resp = c.flush_index("t_unit", "i_1")
    assert resp.flushed is True
    req = httpx_mock.get_request()
    assert req is not None
    # The server's ContentTypeMiddleware rejects body-less POSTs without
    # the JSON content type; the SDK sends ``{}`` to satisfy it.
    assert req.headers["Content-Type"] == "application/json"
    assert req.content == b"{}"


def test_compact_index_sends_json_content_type(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/compact",
        method="POST",
        json={
            "index_id": "i_1",
            "status": "compacting",
            "message": "Index compaction started",
        },
    )
    with make_client(url) as c:
        resp = c.compact_index("t_unit", "i_1")
    assert resp["status"] == "compacting"
    req = httpx_mock.get_request()
    assert req is not None
    assert req.headers["Content-Type"] == "application/json"
    assert req.content == b"{}"


def test_rebuild_graph_round_trip(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/rebuild-graph",
        method="POST",
        json={"rebuilt": True, "chunks": 52000, "wall_ms": 1234},
    )
    with make_client(url) as c:
        resp = c.rebuild_graph("t_unit", "i_1")
    assert resp.rebuilt is True
    assert resp.chunks == 52000
    assert resp.wall_ms == 1234


def test_rebuild_graph_409_raises_conflict(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/rebuild-graph",
        method="POST",
        status_code=409,
        json={
            "error": {
                "code": "conflict",
                "message": "compaction already in progress for this index",
            }
        },
    )
    with make_client(url) as c, pytest.raises(ConflictError) as exc_info:
        c.rebuild_graph("t_unit", "i_1")
    assert exc_info.value.status_code == 409


def test_search_passes_ef_search(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/search",
        method="POST",
        json={"results": [], "total": 0},
    )
    with make_client(url) as c:
        c.search("t_unit", "i_1", query="hello", k=5, ef_search=256)
    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body == {"query": "hello", "k": 5, "ef_search": 256}


def test_search_full_parses_sharded_fields(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/search",
        method="POST",
        json={
            "results": [{"id": "c1", "score": 0.9}],
            "total": 1,
            "partial": True,
            "shards_total": 3,
            "shards_ok": 2,
            "degraded_shards": ["shard-2"],
        },
    )
    with make_client(url) as c:
        resp = c.search_full("t_unit", "i_1", query="hello")
    assert resp.total == 1
    assert resp.results[0].id == "c1"
    assert resp.partial is True
    assert resp.shards_total == 3
    assert resp.shards_ok == 2
    assert resp.degraded_shards == ["shard-2"]


def test_search_full_local_path_leaves_shard_fields_none(
    httpx_mock: HTTPXMock, url: str
) -> None:
    # Non-sharded deployments return exactly {"results", "total"}.
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/indexes/i_1/search",
        method="POST",
        json={"results": [], "total": 0},
    )
    with make_client(url) as c:
        resp = c.search_full("t_unit", "i_1", query="hello")
    assert resp.partial is None
    assert resp.shards_total is None
    assert resp.shards_ok is None
    assert resp.degraded_shards is None


def test_cleanup_orphans_passes_min_age_and_dry_run(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/admin/cleanup-orphans?min_age=24h&dry_run=true",
        method="POST",
        json={
            "removed": ["/data/tenants/t/indexes/i.pre-reembed.20260101T000000Z"],
            "freed_bytes": 0,
            "min_age": "24h0m0s",
            "dry_run": True,
        },
    )
    with make_client(url) as c:
        resp = c.cleanup_orphans(min_age="24h", dry_run=True)
    assert resp.dry_run is True
    assert resp.min_age == "24h0m0s"
    assert len(resp.removed) == 1

    sent = httpx_mock.get_request()
    assert sent is not None
    assert sent.url.params.get("min_age") == "24h"
    assert sent.url.params.get("dry_run") == "true"


def test_create_api_key_sends_user_id_and_name_parses_plaintext(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/api-keys",
        method="POST",
        json={
            "id": "k_1",
            "name": "ci-key",
            "user_id": "u_1",
            "plaintext": "sk_live_secret_once",
            "created_at": "2026-06-17T00:00:00Z",
        },
        status_code=201,
    )
    with make_client(url) as c:
        key = c.create_api_key("t_unit", name="ci-key", user_id="u_1")
    assert key.id == "k_1"
    assert key.name == "ci-key"
    assert key.user_id == "u_1"
    # The one-time secret lives under the "plaintext" json tag.
    assert key.plaintext == "sk_live_secret_once"

    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    # Server reads both fields; user_id may be empty but is always sent.
    assert body == {"user_id": "u_1", "name": "ci-key"}


def test_create_api_key_empty_user_id_still_sent(
    httpx_mock: HTTPXMock, url: str
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/api-keys",
        method="POST",
        json={"id": "k_2", "name": "tenant-key", "user_id": "", "plaintext": "x"},
        status_code=201,
    )
    with make_client(url) as c:
        c.create_api_key("t_unit", name="tenant-key")

    req = httpx_mock.get_request()
    assert req is not None
    body = json.loads(req.content)
    assert body == {"user_id": "", "name": "tenant-key"}


def test_list_api_keys_parses_api_keys_wrapper(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/api-keys",
        method="GET",
        json={
            "api_keys": [
                {
                    "id": "k_1",
                    "user_id": "u_1",
                    "name": "ci-key",
                    "created_at": "2026-06-17T00:00:00Z",
                    "last_used_at": "2026-06-17T01:00:00Z",
                }
            ]
        },
    )
    with make_client(url) as c:
        listing = c.list_api_keys("t_unit")
    # Wrapper key is "api_keys", not "keys".
    assert len(listing.api_keys) == 1
    item = listing.api_keys[0]
    assert item.id == "k_1"
    assert item.name == "ci-key"
    assert item.user_id == "u_1"
    # List items never carry the plaintext secret.
    assert item.plaintext is None


def test_revoke_api_key_deletes_by_id(httpx_mock: HTTPXMock, url: str) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants/t_unit/api-keys/k_1",
        method="DELETE",
        json={"revoked": True},
    )
    with make_client(url) as c:
        out = c.revoke_api_key("t_unit", "k_1")
    assert isinstance(out, dict)
