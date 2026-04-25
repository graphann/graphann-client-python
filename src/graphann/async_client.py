"""Asynchronous GraphANN client.

Mirrors :class:`graphann.client.Client` method-for-method, but is built
on ``httpx.AsyncClient`` and uses ``asyncio.sleep`` for retries. Method
signatures are identical apart from ``async def`` / ``await``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    # ``typing.Self`` lands in 3.11; ``typing_extensions`` is shipped by
    # pydantic so it's always present at runtime, but we only need ``Self``
    # for type-checking — runtime callers see a forward-reference string
    # because of ``from __future__ import annotations``.
    from typing_extensions import Self

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as _PydanticValidationError

from . import models as M
from ._cache import ResponseCache, make_cache_key
from ._http import (
    DEFAULT_GZIP_THRESHOLD,
    DEFAULT_LIMITS,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
    MetricsHook,
    RequestPlan,
    build_request,
    is_retriable_transport_error,
    parse_retry_after,
    process_response,
    safe_metrics,
    wrap_transport_error,
)
from ._retry import RetryPolicy, compute_delay
from ._singleflight import AsyncSingleflight
from .errors import ValidationError
from .pagination import AsyncPageIterator

__all__ = ["AsyncClient"]

T = TypeVar("T", bound=BaseModel)


class AsyncClient:
    """Asynchronous client for the GraphANN HTTP API.

    Method surface matches :class:`graphann.client.Client`. Construct
    with ``async with AsyncClient(...) as ac:`` so the underlying
    ``httpx.AsyncClient`` connection pool is closed deterministically.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:38888",
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: httpx.Timeout | float | None = None,
        max_retries: int = 3,
        retry_policy: RetryPolicy | None = None,
        cache_ttl: float | None = None,
        cache_max_entries: int = 256,
        gzip_threshold: int = DEFAULT_GZIP_THRESHOLD,
        metrics_hook: MetricsHook | None = None,
        user_agent: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        verify: bool | str = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.gzip_threshold = gzip_threshold
        self.metrics_hook = metrics_hook

        if retry_policy is not None:
            self._retry = retry_policy
        else:
            self._retry = RetryPolicy(max_retries=max_retries)

        self._cache: ResponseCache | None
        if cache_ttl is not None and cache_ttl > 0:
            self._cache = ResponseCache(ttl=cache_ttl, max_entries=cache_max_entries)
        else:
            self._cache = None

        self._singleflight = AsyncSingleflight()

        if isinstance(timeout, httpx.Timeout):
            httpx_timeout: httpx.Timeout = timeout
        elif isinstance(timeout, (int, float)):
            httpx_timeout = httpx.Timeout(float(timeout))
        else:
            httpx_timeout = DEFAULT_TIMEOUT

        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx_timeout,
            limits=DEFAULT_LIMITS,
            transport=transport,
            verify=verify,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying httpx connection pool."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal request plumbing
    # ------------------------------------------------------------------

    def _build_plan(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: Mapping[str, Any] | None = None,
        tenant_override: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RequestPlan:
        return build_request(
            method,
            self.base_url,
            path,
            api_key=self.api_key,
            tenant_id=tenant_override or self.tenant_id,
            user_agent=self.user_agent,
            body=body,
            params=params,
            extra_headers=extra_headers,
            gzip_threshold=self.gzip_threshold,
        )

    async def _send(self, plan: RequestPlan) -> Any:
        attempt = 0
        start = time.monotonic()
        while True:
            try:
                response = await self._http.request(
                    plan.method,
                    plan.url,
                    headers=plan.headers,
                    params=plan.params or None,
                    content=plan.body,
                )
            except httpx.HTTPError as exc:
                if (
                    not is_retriable_transport_error(exc)
                    or attempt >= self._retry.max_retries
                ):
                    safe_metrics(
                        self.metrics_hook,
                        "graphann.http.request_error_total",
                        1.0,
                        {"method": plan.method, "kind": "transport"},
                    )
                    raise wrap_transport_error(exc) from exc
                delay = compute_delay(attempt, self._retry)
                await asyncio.sleep(delay)
                attempt += 1
                continue

            status = response.status_code
            if (
                status in self._retry.retry_on_status
                and attempt < self._retry.max_retries
            ):
                retry_after: float | None = None
                if status in (429, 503):
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                delay = compute_delay(attempt, self._retry, retry_after=retry_after)
                await response.aclose()
                await asyncio.sleep(delay)
                attempt += 1
                continue

            duration = time.monotonic() - start
            safe_metrics(
                self.metrics_hook,
                "graphann.http.request_duration_seconds",
                duration,
                {"method": plan.method, "status": str(status)},
            )
            return process_response(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: Mapping[str, Any] | None = None,
        tenant_override: str | None = None,
        cacheable: bool = False,
        coalesce: bool = False,
    ) -> Any:
        plan = self._build_plan(
            method, path, body=body, params=params, tenant_override=tenant_override
        )
        cache_key: str | None = None
        if cacheable and self._cache is not None and method.upper() in {"GET", "POST"}:
            cache_key = make_cache_key(
                method, path, plan.cache_payload(), self.tenant_id
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        if coalesce:
            sf_key = make_cache_key(method, path, plan.cache_payload(), self.tenant_id)
            result = await self._singleflight.call(sf_key, lambda: self._send(plan))
        else:
            result = await self._send(plan)

        if cache_key is not None and self._cache is not None:
            self._cache.set(cache_key, result)
        return result

    @staticmethod
    def _validate(model: type[T], data: Any) -> T:
        try:
            return model.model_validate(data)
        except _PydanticValidationError as exc:
            raise ValidationError(
                f"server response did not match {model.__name__}",
                pydantic_error=exc,
            ) from exc

    @staticmethod
    def _dump(model: BaseModel) -> dict[str, Any]:
        return model.model_dump(mode="json", exclude_none=True)

    def _invalidate_search_cache(self) -> None:
        if self._cache is not None:
            self._cache.clear()

    @staticmethod
    def _document_payload(
        documents: Iterable[M.DocumentInput | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for doc in documents:
            if isinstance(doc, M.DocumentInput):
                out.append(doc.model_dump(mode="json", exclude_none=True))
            elif isinstance(doc, dict):
                model = M.DocumentInput.model_validate(doc)
                out.append(model.model_dump(mode="json", exclude_none=True))
            else:
                raise TypeError(f"unsupported document type: {type(doc).__name__}")
        return out

    # ==================================================================
    # Health
    # ==================================================================

    async def health(self) -> M.Health:
        return self._validate(M.Health, await self._request("GET", "/health"))

    async def ready(self) -> M.Health:
        return self._validate(M.Health, await self._request("GET", "/ready"))

    # ==================================================================
    # Tenants
    # ==================================================================

    async def list_tenants(self) -> list[M.Tenant]:
        data = await self._request("GET", "/v1/tenants", cacheable=True)
        return self._validate(M.TenantList, data).tenants

    async def create_tenant(self, name: str, *, id: str | None = None) -> M.Tenant:
        body = self._dump(M.CreateTenantRequest(name=name, id=id))
        data = await self._request("POST", "/v1/tenants", body=body)
        self._invalidate_search_cache()
        return self._validate(M.Tenant, data)

    async def get_tenant(self, tenant_id: str) -> M.Tenant:
        data = await self._request("GET", f"/v1/tenants/{tenant_id}", cacheable=True)
        return self._validate(M.Tenant, data)

    async def delete_tenant(self, tenant_id: str) -> dict[str, Any]:
        data = await self._request("DELETE", f"/v1/tenants/{tenant_id}")
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # Indexes
    # ==================================================================

    async def list_indexes(self, tenant_id: str) -> list[M.Index]:
        data = await self._request(
            "GET", f"/v1/tenants/{tenant_id}/indexes", cacheable=True
        )
        return self._validate(M.IndexList, data).indexes

    async def create_index(
        self,
        tenant_id: str,
        name: str,
        *,
        description: str | None = None,
        id: str | None = None,
    ) -> M.Index:
        body = self._dump(
            M.CreateIndexRequest(name=name, description=description, id=id)
        )
        data = await self._request(
            "POST", f"/v1/tenants/{tenant_id}/indexes", body=body
        )
        self._invalidate_search_cache()
        return self._validate(M.Index, data)

    async def get_index(self, tenant_id: str, index_id: str) -> M.Index:
        data = await self._request(
            "GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}", cacheable=True
        )
        return self._validate(M.Index, data)

    async def update_index(
        self,
        tenant_id: str,
        index_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> M.Index:
        body = self._dump(M.UpdateIndexRequest(name=name, description=description))
        data = await self._request(
            "PATCH", f"/v1/tenants/{tenant_id}/indexes/{index_id}", body=body
        )
        self._invalidate_search_cache()
        return self._validate(M.Index, data)

    async def delete_index(self, tenant_id: str, index_id: str) -> None:
        await self._request("DELETE", f"/v1/tenants/{tenant_id}/indexes/{index_id}")
        self._invalidate_search_cache()

    async def get_index_status(self, tenant_id: str, index_id: str) -> M.IndexStatus:
        data = await self._request(
            "GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}/status"
        )
        return self._validate(M.IndexStatus, data)

    async def get_live_stats(self, tenant_id: str, index_id: str) -> M.LiveIndexStats:
        data = await self._request(
            "GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}/live-stats"
        )
        return self._validate(M.LiveIndexStats, data)

    async def build_index(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = await self._request(
            "POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/build"
        )
        return data if isinstance(data, dict) else {}

    async def compact_index(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = await self._request(
            "POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/compact"
        )
        return data if isinstance(data, dict) else {}

    async def clear_index(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = await self._request(
            "POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/clear"
        )
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # Documents
    # ==================================================================

    async def add_documents(
        self,
        tenant_id: str,
        index_id: str,
        documents: Iterable[M.DocumentInput | dict[str, Any]],
    ) -> M.AddDocumentsResponse:
        payload = {"documents": self._document_payload(documents)}
        data = await self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents",
            body=payload,
        )
        self._invalidate_search_cache()
        return self._validate(M.AddDocumentsResponse, data)

    async def import_documents(
        self,
        tenant_id: str,
        index_id: str,
        documents: Iterable[M.DocumentInput | dict[str, Any]],
    ) -> M.ImportDocumentsResponse:
        payload = {"documents": self._document_payload(documents)}
        data = await self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/import",
            body=payload,
        )
        self._invalidate_search_cache()
        return self._validate(M.ImportDocumentsResponse, data)

    async def get_pending_status(
        self, tenant_id: str, index_id: str
    ) -> M.PendingStatus:
        data = await self._request(
            "GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}/pending"
        )
        return self._validate(M.PendingStatus, data)

    async def process_pending(
        self, tenant_id: str, index_id: str
    ) -> M.ProcessPendingResponse:
        data = await self._request(
            "POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/process"
        )
        self._invalidate_search_cache()
        return self._validate(M.ProcessPendingResponse, data)

    async def clear_pending(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = await self._request(
            "DELETE", f"/v1/tenants/{tenant_id}/indexes/{index_id}/pending"
        )
        return data if isinstance(data, dict) else {}

    async def get_document(
        self, tenant_id: str, index_id: str, document_id: int | str
    ) -> M.Document:
        data = await self._request(
            "GET",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents/{document_id}",
        )
        return self._validate(M.Document, data)

    async def delete_document(
        self, tenant_id: str, index_id: str, document_id: int | str
    ) -> dict[str, Any]:
        data = await self._request(
            "DELETE",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents/{document_id}",
        )
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    def list_documents(
        self,
        tenant_id: str,
        index_id: str,
        *,
        prefix: str | None = None,
        page_size: int = 100,
    ) -> AsyncPageIterator[M.DocumentListEntry]:
        async def fetch(
            cursor: str | None,
        ) -> tuple[list[M.DocumentListEntry], str | None]:
            params: dict[str, Any] = {"limit": page_size}
            if prefix:
                params["prefix"] = prefix
            if cursor:
                params["cursor"] = cursor
            data = await self._request(
                "GET",
                f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents",
                params=params,
            )
            page = self._validate(M.DocumentListPage, data)
            return list(page.documents), page.next_cursor

        return AsyncPageIterator(fetch)

    async def bulk_delete_documents(
        self, tenant_id: str, index_id: str, document_ids: list[int]
    ) -> M.BulkDeleteResponse:
        body = self._dump(M.BulkDeleteRequest(document_ids=document_ids))
        data = await self._request(
            "DELETE",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.BulkDeleteResponse, data)

    async def bulk_delete_by_external_ids(
        self, tenant_id: str, index_id: str, external_ids: list[str]
    ) -> M.BulkDeleteByExternalIdsResponse:
        body = self._dump(M.BulkDeleteByExternalIdsRequest(external_ids=external_ids))
        data = await self._request(
            "DELETE",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents/by-external-id",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.BulkDeleteByExternalIdsResponse, data)

    async def cleanup_orphans(self) -> M.CleanupOrphansResponse:
        data = await self._request("POST", "/v1/admin/cleanup-orphans")
        return self._validate(M.CleanupOrphansResponse, data)

    # ==================================================================
    # Chunks
    # ==================================================================

    async def get_chunk(
        self, tenant_id: str, index_id: str, chunk_id: int | str
    ) -> M.Chunk:
        """``GET /v1/tenants/{tenantID}/indexes/{indexID}/chunks/{chunkID}``."""
        data = await self._request(
            "GET",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/chunks/{chunk_id}",
        )
        return self._validate(M.Chunk, data)

    async def delete_chunks(
        self, tenant_id: str, index_id: str, chunk_ids: list[int]
    ) -> M.DeleteChunksResponse:
        """``DELETE /v1/tenants/{tenantID}/indexes/{indexID}/chunks/{chunkID}``.

        Single call with ``{"chunk_ids": [...]}`` body and a placeholder path
        id; matches the Go SDK ``DeleteChunks`` semantics.
        """
        if not chunk_ids:
            raise ValueError("delete_chunks requires at least one chunk id")
        body = {"chunk_ids": list(chunk_ids)}
        data = await self._request(
            "DELETE",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/chunks/0",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.DeleteChunksResponse, data)

    # ==================================================================
    # Search
    # ==================================================================

    async def search(
        self,
        tenant_id: str,
        index_id: str,
        *,
        query: str | None = None,
        vector: list[float] | None = None,
        k: int | None = 10,
        filter: M.SearchFilter | dict[str, Any] | None = None,
        coalesce: bool = True,
        cache: bool = True,
    ) -> list[M.SearchResult]:
        if query is None and vector is None:
            raise ValueError("search requires either query or vector")
        body = M.SearchRequest(
            query=query, vector=vector, k=k, filter=_coerce_filter(filter)
        )
        data = await self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/search",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.SearchResponse, data).results

    async def search_text(
        self,
        tenant_id: str,
        index_id: str,
        query: str,
        *,
        k: int | None = 10,
        filter: M.SearchFilter | dict[str, Any] | None = None,
        coalesce: bool = True,
        cache: bool = True,
    ) -> list[M.SearchResult]:
        body = M.SearchRequest(query=query, k=k, filter=_coerce_filter(filter))
        data = await self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/search/text",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.SearchResponse, data).results

    async def search_vector(
        self,
        tenant_id: str,
        index_id: str,
        vector: list[float],
        *,
        k: int | None = 10,
        filter: M.SearchFilter | dict[str, Any] | None = None,
        coalesce: bool = True,
        cache: bool = True,
    ) -> list[M.SearchResult]:
        body = M.SearchRequest(vector=vector, k=k, filter=_coerce_filter(filter))
        data = await self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/search/vector",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.SearchResponse, data).results

    # ------------------------------------------------------------------
    # Org-level
    # ------------------------------------------------------------------

    async def sync_documents(
        self,
        org_id: str,
        *,
        user_id: str,
        source_type: str,
        shared: bool,
        documents: Iterable[M.OrgSyncDocument | dict[str, Any]],
    ) -> M.OrgSyncResponse:
        payload_docs: list[dict[str, Any]] = []
        for doc in documents:
            if isinstance(doc, M.OrgSyncDocument):
                payload_docs.append(doc.model_dump(mode="json", exclude_none=True))
            elif isinstance(doc, dict):
                model = M.OrgSyncDocument.model_validate(doc)
                payload_docs.append(model.model_dump(mode="json", exclude_none=True))
            else:
                raise TypeError(f"unsupported document type: {type(doc).__name__}")
        body = {
            "user_id": user_id,
            "source_type": source_type,
            "shared": shared,
            "documents": payload_docs,
        }
        data = await self._request("POST", f"/v1/orgs/{org_id}/documents", body=body)
        self._invalidate_search_cache()
        return self._validate(M.OrgSyncResponse, data)

    async def multi_search(
        self,
        org_id: str,
        user_id: str,
        query: str,
        *,
        k: int | None = None,
        sources: list[str] | None = None,
        ef_search: int | None = None,
        include_text: bool | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        distance_threshold: float | None = None,
        coalesce: bool = True,
        cache: bool = True,
    ) -> M.MultiSearchResponse:
        body = M.MultiSearchRequest(
            query=query,
            k=k,
            sources=sources,
            ef_search=ef_search,
            include_text=include_text,
            start_time=start_time,
            end_time=end_time,
            distance_threshold=distance_threshold,
        )
        data = await self._request(
            "POST",
            f"/v1/orgs/{org_id}/users/{user_id}/search",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.MultiSearchResponse, data)

    async def list_user_indexes(self, org_id: str, user_id: str) -> M.OrgIndexList:
        data = await self._request(
            "GET", f"/v1/orgs/{org_id}/users/{user_id}/indexes", cacheable=True
        )
        return self._validate(M.OrgIndexList, data)

    async def list_shared_indexes(self, org_id: str) -> M.OrgIndexList:
        data = await self._request(
            "GET", f"/v1/orgs/{org_id}/shared/indexes", cacheable=True
        )
        return self._validate(M.OrgIndexList, data)

    # ==================================================================
    # Hot model switching / jobs
    # ==================================================================

    async def switch_embedding_model(
        self,
        tenant_id: str,
        index_id: str,
        *,
        embedding_backend: str,
        model: str,
        dimension: int,
        endpoint_override: str | None = None,
        api_key: str | None = None,
    ) -> M.HotModelSwitchResponse:
        body = self._dump(
            M.HotModelSwitchRequest(
                embedding_backend=embedding_backend,  # type: ignore[arg-type]
                model=model,
                dimension=dimension,
                endpoint_override=endpoint_override,
                api_key=api_key,
            )
        )
        data = await self._request(
            "PATCH",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/embedding-model",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.HotModelSwitchResponse, data)

    async def get_job(self, job_id: str) -> M.Job:
        data = await self._request("GET", f"/v1/jobs/{job_id}")
        return self._validate(M.Job, data)

    def list_jobs(
        self,
        tenant_id: str | None = None,
        *,
        status: str | None = None,
        page_size: int | None = None,
    ) -> AsyncPageIterator[M.Job]:
        path = f"/v1/tenants/{tenant_id}/jobs" if tenant_id else "/v1/jobs"

        async def fetch(cursor: str | None) -> tuple[list[M.Job], str | None]:
            params: dict[str, Any] = {}
            if status:
                params["status"] = status
            if page_size:
                params["limit"] = page_size
            if cursor:
                params["cursor"] = cursor
            data = await self._request("GET", path, params=params)
            page = self._validate(M.JobList, data)
            return list(page.jobs), page.next_cursor

        return AsyncPageIterator(fetch)

    # ==================================================================
    # Cluster
    # ==================================================================

    async def get_cluster_nodes(self) -> M.ClusterNodeList:
        data = await self._request("GET", "/v1/cluster/nodes", cacheable=True)
        return self._validate(M.ClusterNodeList, data)

    async def get_cluster_shards(self) -> M.ClusterShardList:
        data = await self._request("GET", "/v1/cluster/shards", cacheable=True)
        return self._validate(M.ClusterShardList, data)

    async def get_cluster_health(self) -> M.ClusterHealth:
        data = await self._request("GET", "/v1/cluster/health")
        return self._validate(M.ClusterHealth, data)

    # ==================================================================
    # LLM settings
    # ==================================================================

    async def get_llm_settings(self, org_id: str) -> M.LLMSettings:
        """``GET /v1/orgs/{orgID}/llm-settings`` (api_key returned masked)."""
        data = await self._request(
            "GET", f"/v1/orgs/{org_id}/llm-settings", cacheable=True
        )
        return self._validate(M.LLMSettings, data)

    async def update_llm_settings(
        self, org_id: str, settings: M.LLMSettings | dict[str, Any]
    ) -> M.LLMSettings:
        """``PATCH /v1/orgs/{orgID}/llm-settings`` — partial-merge update.

        Only fields present in ``settings`` are overwritten. Server returns
        the merged settings with ``api_key`` masked. Return type changed
        from envelope (pre-0.1.1) to raw ``LLMSettings`` (0.1.1+).
        """
        if isinstance(settings, dict):
            settings = M.LLMSettings.model_validate(settings)
        body = settings.model_dump(mode="json", exclude_none=True)
        data = await self._request(
            "PATCH", f"/v1/orgs/{org_id}/llm-settings", body=body
        )
        self._invalidate_search_cache()
        return self._validate(M.LLMSettings, data)

    async def delete_llm_settings(self, org_id: str) -> dict[str, Any]:
        """``DELETE /v1/orgs/{orgID}/llm-settings`` — reset to defaults."""
        data = await self._request("DELETE", f"/v1/orgs/{org_id}/llm-settings")
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # API keys
    # ==================================================================

    async def create_api_key(
        self, tenant_id: str, user_id: str, *, description: str | None = None
    ) -> M.ApiKey:
        body = self._dump(
            M.CreateApiKeyRequest(user_id=user_id, description=description)
        )
        data = await self._request(
            "POST", f"/v1/tenants/{tenant_id}/api-keys", body=body
        )
        return self._validate(M.ApiKey, data)

    async def list_api_keys(self, tenant_id: str) -> M.ApiKeyList:
        data = await self._request(
            "GET", f"/v1/tenants/{tenant_id}/api-keys", cacheable=True
        )
        return self._validate(M.ApiKeyList, data)

    async def revoke_api_key(self, tenant_id: str, key_id: str) -> dict[str, Any]:
        data = await self._request(
            "DELETE", f"/v1/tenants/{tenant_id}/api-keys/{key_id}"
        )
        return data if isinstance(data, dict) else {}


def _coerce_filter(
    value: M.SearchFilter | dict[str, Any] | None,
) -> M.SearchFilter | None:
    if value is None:
        return None
    if isinstance(value, M.SearchFilter):
        return value
    return M.SearchFilter.model_validate(value)
