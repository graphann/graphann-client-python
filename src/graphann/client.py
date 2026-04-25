"""Synchronous GraphANN client.

The client is built around an httpx ``Client`` with hardened defaults.
It is safe to share a single instance across threads, but callers that
spawn many threads should still use the context-manager form so the
underlying connection pool is closed deterministically.

All public methods return Pydantic models or primitives; raw JSON
responses are not exposed.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
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
from ._singleflight import Singleflight
from .errors import ValidationError
from .pagination import PageIterator

__all__ = ["Client"]

T = TypeVar("T", bound=BaseModel)


class Client:
    """Synchronous client for the GraphANN HTTP API.

    Parameters:
        base_url: Root URL (no trailing path). Defaults to
            ``http://localhost:38888`` for local development.
        api_key: Optional API key. Sent as ``X-API-Key`` and
            ``Authorization: Bearer``.
        tenant_id: Optional default tenant ID. Sent as ``X-Tenant-ID``.
            Tenant-scoped methods (``list_indexes``, ``search``, ...)
            still take a ``tenant_id`` argument; this default is a
            convenience for deployments where every request is for the
            same tenant.
        timeout: Either an ``httpx.Timeout`` instance or ``None`` to use
            the SDK default (5s connect, 30s read/write, 5s pool).
        max_retries: Maximum retry attempts on retriable failures
            (429, 5xx, transport errors). Set to 0 to disable.
        retry_policy: Full :class:`RetryPolicy` override.
        cache_ttl: When set, search/list responses are cached for this
            many seconds.
        cache_max_entries: Cache size cap. Defaults to 256.
        gzip_threshold: Minimum body size (bytes) before requests are
            gzip-encoded. Set to 0 to disable.
        metrics_hook: Optional callable invoked on each request with
            ``(name, value, labels)``.
        transport: Optional ``httpx.BaseTransport`` for tests.
        verify: TLS verification flag forwarded to httpx.
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
        transport: httpx.BaseTransport | None = None,
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

        self._singleflight = Singleflight()

        # httpx timeout normalisation: accept None, float, or Timeout.
        if isinstance(timeout, httpx.Timeout):
            httpx_timeout: httpx.Timeout = timeout
        elif isinstance(timeout, (int, float)):
            httpx_timeout = httpx.Timeout(float(timeout))
        else:
            httpx_timeout = DEFAULT_TIMEOUT

        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx_timeout,
            limits=DEFAULT_LIMITS,
            transport=transport,
            verify=verify,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

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

    def _send(self, plan: RequestPlan) -> Any:
        """Send ``plan`` honouring retries, returning the parsed body.

        Retries are applied to:

        - HTTP 429 (rate-limited) — ``Retry-After`` is honoured.
        - HTTP 502, 503, 504 — same backoff schedule.
        - Transport errors (``httpx.ConnectError``, timeouts, etc.).
        """
        attempt = 0
        last_exc: BaseException | None = None
        start = time.monotonic()
        while True:
            try:
                response = self._http.request(
                    plan.method,
                    plan.url,
                    headers=plan.headers,
                    params=plan.params or None,
                    content=plan.body,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if not is_retriable_transport_error(exc) or attempt >= self._retry.max_retries:
                    safe_metrics(
                        self.metrics_hook,
                        "graphann.http.request_error_total",
                        1.0,
                        {"method": plan.method, "kind": "transport"},
                    )
                    raise wrap_transport_error(exc) from exc
                delay = compute_delay(attempt, self._retry)
                time.sleep(delay)
                attempt += 1
                continue

            status = response.status_code
            if status in self._retry.retry_on_status and attempt < self._retry.max_retries:
                retry_after: float | None = None
                if status in (429, 503):
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                delay = compute_delay(attempt, self._retry, retry_after=retry_after)
                # Buffer + close so the connection is released before sleep.
                response.close()
                time.sleep(delay)
                attempt += 1
                continue

            duration = time.monotonic() - start
            safe_metrics(
                self.metrics_hook,
                "graphann.http.request_duration_seconds",
                duration,
                {"method": plan.method, "status": str(status)},
            )
            # last_exc is unused on the success branch but retained so
            # diagnostic tooling can pick it up via locals if needed.
            del last_exc
            return process_response(response)

    def _request(
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
            cache_key = make_cache_key(method, path, plan.cache_payload(), self.tenant_id)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        if coalesce:
            sf_key = make_cache_key(method, path, plan.cache_payload(), self.tenant_id)
            result = self._singleflight.call(sf_key, lambda: self._send(plan))
        else:
            result = self._send(plan)

        if cache_key is not None and self._cache is not None:
            self._cache.set(cache_key, result)
        return result

    @staticmethod
    def _validate(model: type[T], data: Any) -> T:
        """Validate ``data`` against ``model``, wrapping pydantic errors."""
        try:
            return model.model_validate(data)
        except _PydanticValidationError as exc:
            raise ValidationError(
                f"server response did not match {model.__name__}",
                pydantic_error=exc,
            ) from exc

    @staticmethod
    def _dump(model: BaseModel) -> dict[str, Any]:
        """Serialise a request model dropping None fields."""
        return model.model_dump(mode="json", exclude_none=True)

    def _invalidate_search_cache(self) -> None:
        """Drop the entire response cache.

        Called on operations that change index contents — embeddings,
        documents added/removed, model swapped — so subsequent reads
        don't return stale data.
        """
        if self._cache is not None:
            self._cache.clear()

    # ==================================================================
    # Health
    # ==================================================================

    def health(self) -> M.Health:
        """``GET /health``."""
        return self._validate(M.Health, self._request("GET", "/health"))

    def ready(self) -> M.Health:
        """``GET /ready``."""
        return self._validate(M.Health, self._request("GET", "/ready"))

    # ==================================================================
    # Tenants
    # ==================================================================

    def list_tenants(self) -> list[M.Tenant]:
        """``GET /v1/tenants``. Returns the parsed tenant list."""
        data = self._request("GET", "/v1/tenants", cacheable=True)
        return self._validate(M.TenantList, data).tenants

    def create_tenant(self, name: str, *, id: str | None = None) -> M.Tenant:
        """``POST /v1/tenants``."""
        body = self._dump(M.CreateTenantRequest(name=name, id=id))
        data = self._request("POST", "/v1/tenants", body=body)
        self._invalidate_search_cache()
        return self._validate(M.Tenant, data)

    def get_tenant(self, tenant_id: str) -> M.Tenant:
        """``GET /v1/tenants/{tenantID}``."""
        data = self._request("GET", f"/v1/tenants/{tenant_id}", cacheable=True)
        return self._validate(M.Tenant, data)

    def delete_tenant(self, tenant_id: str) -> dict[str, Any]:
        """``DELETE /v1/tenants/{tenantID}``."""
        data = self._request("DELETE", f"/v1/tenants/{tenant_id}")
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # Indexes
    # ==================================================================

    def list_indexes(self, tenant_id: str) -> list[M.Index]:
        data = self._request("GET", f"/v1/tenants/{tenant_id}/indexes", cacheable=True)
        return self._validate(M.IndexList, data).indexes

    def create_index(
        self,
        tenant_id: str,
        name: str,
        *,
        description: str | None = None,
        id: str | None = None,
    ) -> M.Index:
        body = self._dump(M.CreateIndexRequest(name=name, description=description, id=id))
        data = self._request("POST", f"/v1/tenants/{tenant_id}/indexes", body=body)
        self._invalidate_search_cache()
        return self._validate(M.Index, data)

    def get_index(self, tenant_id: str, index_id: str) -> M.Index:
        data = self._request("GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}", cacheable=True)
        return self._validate(M.Index, data)

    def update_index(
        self,
        tenant_id: str,
        index_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> M.Index:
        body = self._dump(M.UpdateIndexRequest(name=name, description=description))
        data = self._request("PATCH", f"/v1/tenants/{tenant_id}/indexes/{index_id}", body=body)
        self._invalidate_search_cache()
        return self._validate(M.Index, data)

    def delete_index(self, tenant_id: str, index_id: str) -> None:
        self._request("DELETE", f"/v1/tenants/{tenant_id}/indexes/{index_id}")
        self._invalidate_search_cache()

    def get_index_status(self, tenant_id: str, index_id: str) -> M.IndexStatus:
        data = self._request("GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}/status")
        return self._validate(M.IndexStatus, data)

    def get_live_stats(self, tenant_id: str, index_id: str) -> M.LiveIndexStats:
        data = self._request("GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}/live-stats")
        return self._validate(M.LiveIndexStats, data)

    def build_index(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = self._request("POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/build")
        return data if isinstance(data, dict) else {}

    def compact_index(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = self._request("POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/compact")
        return data if isinstance(data, dict) else {}

    def clear_index(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = self._request("POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/clear")
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # Documents
    # ==================================================================

    @staticmethod
    def _document_payload(
        documents: Iterable[M.DocumentInput | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Coerce mixed input (models or dicts) into JSON dicts."""
        out: list[dict[str, Any]] = []
        for doc in documents:
            if isinstance(doc, M.DocumentInput):
                out.append(doc.model_dump(mode="json", exclude_none=True))
            elif isinstance(doc, dict):
                # Validate via model to surface schema errors early.
                model = M.DocumentInput.model_validate(doc)
                out.append(model.model_dump(mode="json", exclude_none=True))
            else:
                raise TypeError(f"unsupported document type: {type(doc).__name__}")
        return out

    def add_documents(
        self,
        tenant_id: str,
        index_id: str,
        documents: Iterable[M.DocumentInput | dict[str, Any]],
    ) -> M.AddDocumentsResponse:
        """``POST /v1/tenants/{tenantID}/indexes/{indexID}/documents``."""
        payload = {"documents": self._document_payload(documents)}
        data = self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents",
            body=payload,
        )
        self._invalidate_search_cache()
        return self._validate(M.AddDocumentsResponse, data)

    def import_documents(
        self,
        tenant_id: str,
        index_id: str,
        documents: Iterable[M.DocumentInput | dict[str, Any]],
    ) -> M.ImportDocumentsResponse:
        """``POST .../import`` — async ingest with auto-processing."""
        payload = {"documents": self._document_payload(documents)}
        data = self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/import",
            body=payload,
        )
        self._invalidate_search_cache()
        return self._validate(M.ImportDocumentsResponse, data)

    def get_pending_status(self, tenant_id: str, index_id: str) -> M.PendingStatus:
        data = self._request("GET", f"/v1/tenants/{tenant_id}/indexes/{index_id}/pending")
        return self._validate(M.PendingStatus, data)

    def process_pending(self, tenant_id: str, index_id: str) -> M.ProcessPendingResponse:
        data = self._request("POST", f"/v1/tenants/{tenant_id}/indexes/{index_id}/process")
        self._invalidate_search_cache()
        return self._validate(M.ProcessPendingResponse, data)

    def clear_pending(self, tenant_id: str, index_id: str) -> dict[str, Any]:
        data = self._request("DELETE", f"/v1/tenants/{tenant_id}/indexes/{index_id}/pending")
        return data if isinstance(data, dict) else {}

    def get_document(self, tenant_id: str, index_id: str, document_id: int | str) -> M.Document:
        data = self._request(
            "GET",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents/{document_id}",
        )
        return self._validate(M.Document, data)

    def delete_document(
        self, tenant_id: str, index_id: str, document_id: int | str
    ) -> dict[str, Any]:
        data = self._request(
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
    ) -> PageIterator[M.DocumentListEntry]:
        """Iterate documents by external-id prefix.

        Returns a :class:`PageIterator` so callers can write ``for page
        in client.list_documents(...): ...``.
        """

        def fetch(cursor: str | None) -> tuple[list[M.DocumentListEntry], str | None]:
            params: dict[str, Any] = {"limit": page_size}
            if prefix:
                params["prefix"] = prefix
            if cursor:
                params["cursor"] = cursor
            data = self._request(
                "GET",
                f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents",
                params=params,
            )
            page = self._validate(M.DocumentListPage, data)
            return list(page.documents), page.next_cursor

        return PageIterator(fetch)

    def bulk_delete_documents(
        self, tenant_id: str, index_id: str, document_ids: list[int]
    ) -> M.BulkDeleteResponse:
        body = self._dump(M.BulkDeleteRequest(document_ids=document_ids))
        data = self._request(
            "DELETE",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.BulkDeleteResponse, data)

    def bulk_delete_by_external_ids(
        self, tenant_id: str, index_id: str, external_ids: list[str]
    ) -> M.BulkDeleteByExternalIdsResponse:
        body = self._dump(M.BulkDeleteByExternalIdsRequest(external_ids=external_ids))
        data = self._request(
            "DELETE",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/documents/by-external-id",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.BulkDeleteByExternalIdsResponse, data)

    def cleanup_orphans(self) -> M.CleanupOrphansResponse:
        """``POST /v1/admin/cleanup-orphans`` — admin only."""
        data = self._request("POST", "/v1/admin/cleanup-orphans")
        return self._validate(M.CleanupOrphansResponse, data)

    # ==================================================================
    # Search
    # ==================================================================

    def search(
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
        """Hybrid search. Pass either ``query`` (text) or ``vector``."""
        if query is None and vector is None:
            raise ValueError("search requires either query or vector")
        body = M.SearchRequest(query=query, vector=vector, k=k, filter=_coerce_filter(filter))
        data = self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/search",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.SearchResponse, data).results

    def search_text(
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
        data = self._request(
            "POST",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/search/text",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.SearchResponse, data).results

    def search_vector(
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
        data = self._request(
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

    def sync_documents(
        self,
        org_id: str,
        *,
        user_id: str,
        source_type: str,
        shared: bool,
        documents: Iterable[M.OrgSyncDocument | dict[str, Any]],
    ) -> M.OrgSyncResponse:
        """``POST /v1/orgs/{orgID}/documents`` — org-level sync."""
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
        data = self._request("POST", f"/v1/orgs/{org_id}/documents", body=body)
        self._invalidate_search_cache()
        return self._validate(M.OrgSyncResponse, data)

    def multi_search(
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
        data = self._request(
            "POST",
            f"/v1/orgs/{org_id}/users/{user_id}/search",
            body=self._dump(body),
            cacheable=cache,
            coalesce=coalesce,
        )
        return self._validate(M.MultiSearchResponse, data)

    def list_user_indexes(self, org_id: str, user_id: str) -> M.OrgIndexList:
        data = self._request("GET", f"/v1/orgs/{org_id}/users/{user_id}/indexes", cacheable=True)
        return self._validate(M.OrgIndexList, data)

    def list_shared_indexes(self, org_id: str) -> M.OrgIndexList:
        data = self._request("GET", f"/v1/orgs/{org_id}/shared/indexes", cacheable=True)
        return self._validate(M.OrgIndexList, data)

    # ==================================================================
    # Hot model switching / jobs
    # ==================================================================

    def switch_embedding_model(
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
        """``PATCH /v1/tenants/{tenantID}/indexes/{indexID}/embedding-model``."""
        body = self._dump(
            M.HotModelSwitchRequest(
                embedding_backend=embedding_backend,  # type: ignore[arg-type]
                model=model,
                dimension=dimension,
                endpoint_override=endpoint_override,
                api_key=api_key,
            )
        )
        data = self._request(
            "PATCH",
            f"/v1/tenants/{tenant_id}/indexes/{index_id}/embedding-model",
            body=body,
        )
        self._invalidate_search_cache()
        return self._validate(M.HotModelSwitchResponse, data)

    def get_job(self, job_id: str) -> M.Job:
        data = self._request("GET", f"/v1/jobs/{job_id}")
        return self._validate(M.Job, data)

    def list_jobs(
        self,
        tenant_id: str | None = None,
        *,
        status: str | None = None,
        page_size: int | None = None,
    ) -> PageIterator[M.Job]:
        path = f"/v1/tenants/{tenant_id}/jobs" if tenant_id else "/v1/jobs"

        def fetch(cursor: str | None) -> tuple[list[M.Job], str | None]:
            params: dict[str, Any] = {}
            if status:
                params["status"] = status
            if page_size:
                params["limit"] = page_size
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", path, params=params)
            page = self._validate(M.JobList, data)
            return list(page.jobs), page.next_cursor

        return PageIterator(fetch)

    # ==================================================================
    # Cluster
    # ==================================================================

    def get_cluster_nodes(self) -> M.ClusterNodeList:
        data = self._request("GET", "/v1/cluster/nodes", cacheable=True)
        return self._validate(M.ClusterNodeList, data)

    def get_cluster_shards(self) -> M.ClusterShardList:
        data = self._request("GET", "/v1/cluster/shards", cacheable=True)
        return self._validate(M.ClusterShardList, data)

    def get_cluster_health(self) -> M.ClusterHealth:
        data = self._request("GET", "/v1/cluster/health")
        return self._validate(M.ClusterHealth, data)

    # ==================================================================
    # LLM settings
    # ==================================================================

    def get_llm_settings(self, org_id: str) -> M.LLMSettings:
        data = self._request("GET", f"/v1/orgs/{org_id}/settings/llm", cacheable=True)
        return self._validate(M.LLMSettings, data)

    def update_llm_settings(
        self, org_id: str, settings: M.LLMSettings | dict[str, Any]
    ) -> M.LLMSettingsResponse:
        if isinstance(settings, dict):
            settings = M.LLMSettings.model_validate(settings)
        body = settings.model_dump(mode="json", exclude_none=True)
        data = self._request("PUT", f"/v1/orgs/{org_id}/settings/llm", body=body)
        self._invalidate_search_cache()
        return self._validate(M.LLMSettingsResponse, data)

    def delete_llm_settings(self, org_id: str) -> dict[str, Any]:
        data = self._request("DELETE", f"/v1/orgs/{org_id}/settings/llm")
        self._invalidate_search_cache()
        return data if isinstance(data, dict) else {}

    # ==================================================================
    # API keys
    # ==================================================================

    def create_api_key(
        self, tenant_id: str, user_id: str, *, description: str | None = None
    ) -> M.ApiKey:
        body = self._dump(M.CreateApiKeyRequest(user_id=user_id, description=description))
        data = self._request("POST", f"/v1/tenants/{tenant_id}/api-keys", body=body)
        return self._validate(M.ApiKey, data)

    def list_api_keys(self, tenant_id: str) -> M.ApiKeyList:
        data = self._request("GET", f"/v1/tenants/{tenant_id}/api-keys", cacheable=True)
        return self._validate(M.ApiKeyList, data)

    def revoke_api_key(self, tenant_id: str, key_id: str) -> dict[str, Any]:
        data = self._request("DELETE", f"/v1/tenants/{tenant_id}/api-keys/{key_id}")
        return data if isinstance(data, dict) else {}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _coerce_filter(
    value: M.SearchFilter | dict[str, Any] | None,
) -> M.SearchFilter | None:
    if value is None:
        return None
    if isinstance(value, M.SearchFilter):
        return value
    return M.SearchFilter.model_validate(value)
