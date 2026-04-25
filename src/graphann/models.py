"""Pydantic v2 models for every GraphANN request and response shape.

The models accept extra fields (``model_config = {"extra": "allow"}``) so
forward-compatible server changes do not break existing clients. Outbound
request bodies are strict — ``model_dump(exclude_none=True)`` is used by
the HTTP layer so optional knobs default to whatever the server picks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AddDocumentsResponse",
    "ApiKey",
    "ApiKeyList",
    "BulkDeleteByExternalIdsRequest",
    "BulkDeleteByExternalIdsResponse",
    "BulkDeleteRequest",
    "BulkDeleteResponse",
    "Chunk",
    "CleanupOrphansResponse",
    "ClusterHealth",
    "ClusterNode",
    "ClusterNodeList",
    "ClusterShard",
    "ClusterShardList",
    "CreateApiKeyRequest",
    "CreateIndexRequest",
    "CreateTenantRequest",
    "DeleteChunksResponse",
    "Document",
    "DocumentInput",
    "DocumentListEntry",
    "DocumentListPage",
    "Health",
    "HotModelSwitchRequest",
    "HotModelSwitchResponse",
    "ImportDocumentsResponse",
    "Index",
    "IndexList",
    "IndexStatus",
    "Job",
    "JobList",
    "LLMSettings",
    "LLMSettingsResponse",
    "LiveIndexStats",
    "MultiSearchRequest",
    "MultiSearchResponse",
    "MultiSearchResult",
    "OrgIndexEntry",
    "OrgIndexList",
    "OrgSyncDocument",
    "OrgSyncRequest",
    "OrgSyncResponse",
    "PendingStatus",
    "ProcessPendingResponse",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "Tenant",
    "TenantList",
    "UpdateIndexRequest",
]


class _Loose(BaseModel):
    """Base model that tolerates unknown fields and trims surplus types."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class Health(_Loose):
    """Server health probe response."""

    status: str
    reason: str | None = None


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------


class Tenant(_Loose):
    """Tenant resource."""

    id: str
    name: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    index_count: int | None = None
    metadata: dict[str, str] | None = None


class TenantList(_Loose):
    """Listing envelope returned by ``GET /v1/tenants``."""

    tenants: list[Tenant] = Field(default_factory=list)
    total: int = 0


class CreateTenantRequest(BaseModel):
    """Body for ``POST /v1/tenants``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    id: str | None = None  # optional deterministic id


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


IndexStatusValue = Literal[
    "empty", "building", "ready", "error", "compacting", "cleared"
]


class Index(_Loose):
    """Index resource."""

    id: str
    tenant_id: str | None = None
    name: str | None = None
    description: str | None = None
    status: str | None = None
    num_docs: int | None = None
    num_chunks: int | None = None
    dimension: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IndexList(_Loose):
    indexes: list[Index] = Field(default_factory=list)
    total: int = 0


class CreateIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    id: str | None = None


class UpdateIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class IndexStatus(_Loose):
    index_id: str
    status: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentInput(BaseModel):
    """A document to ingest into an index.

    Either ``text`` or ``content`` is accepted by the server; ``text`` is
    the canonical name. ``id`` becomes the document's external ID.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    text: str
    metadata: dict[str, Any] | None = None
    upsert: bool = False
    expires_at: datetime | None = None
    repo_id: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None


class AddDocumentsResponse(_Loose):
    added: int
    index_id: str
    chunk_ids: list[int] = Field(default_factory=list)


class ImportDocumentsResponse(_Loose):
    imported: int
    index_id: str
    document_ids: list[int] = Field(default_factory=list)
    pending_total: int | None = None
    status: str | None = None
    message: str | None = None


class Document(_Loose):
    """Document detail returned by ``GET /documents/{docID}``."""

    index_id: str | None = None
    document_id: int | None = None
    external_id: str | None = None
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    total_chunks: int | None = None


class DocumentListEntry(_Loose):
    id: str
    text: str | None = None
    metadata: dict[str, Any] | None = None


class DocumentListPage(_Loose):
    documents: list[DocumentListEntry] = Field(default_factory=list)
    next_cursor: str | None = None


class BulkDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[int]


class BulkDeleteResponse(_Loose):
    index_id: str
    documents_deleted: int
    chunks_deleted: int
    deleted_per_doc: dict[str, int] = Field(default_factory=dict)


class BulkDeleteByExternalIdsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_ids: list[str]


class BulkDeleteByExternalIdsResponse(_Loose):
    index_id: str
    documents_deleted: int
    chunks_deleted: int
    deleted_per_id: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Chunks
# ---------------------------------------------------------------------------


class Chunk(_Loose):
    """Chunk detail returned by ``GET /chunks/{chunkID}``."""

    chunk_id: int
    text: str | None = None
    document_id: int | None = None
    chunk_index: int | None = None
    start: int | None = None
    end: int | None = None


class DeleteChunksResponse(_Loose):
    """Response for ``DELETE /chunks/{chunkID}`` (body carries the id list)."""

    deleted: int = 0
    index_id: str | None = None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_ids: list[str] | None = None
    exclude_external_ids: list[str] | None = None
    metadata_filter: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    """Body for ``POST /search`` / ``/search/text`` / ``/search/vector``."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    vector: list[float] | None = None
    k: int | None = None
    filter: SearchFilter | None = None


class SearchResult(_Loose):
    id: str
    text: str | None = None
    score: float = 0.0
    metadata: Any = None


class SearchResponse(_Loose):
    results: list[SearchResult] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Live stats / pending / cleanup
# ---------------------------------------------------------------------------


class LiveIndexStats(_Loose):
    index_id: str
    is_live: bool
    base_chunks: int | None = None
    delta_chunks: int | None = None
    total_chunks: int | None = None
    deleted_chunks: int | None = None
    live_chunks: int | None = None
    documents: int | None = None
    dimension: int | None = None
    is_dirty: bool | None = None
    num_chunks: int | None = None
    num_docs: int | None = None


class PendingStatus(_Loose):
    index_id: str
    pending_count: int


class ProcessPendingResponse(_Loose):
    index_id: str
    processed: int
    chunks_created: int
    chunk_ids: list[int] = Field(default_factory=list)


class CleanupOrphansResponse(_Loose):
    removed: list[str] = Field(default_factory=list)
    freed_bytes: int = 0


# ---------------------------------------------------------------------------
# Hot model switching / jobs
# ---------------------------------------------------------------------------


class HotModelSwitchRequest(BaseModel):
    """Body for ``PATCH /indexes/{id}/embedding-model``."""

    model_config = ConfigDict(extra="forbid")

    embedding_backend: Literal["ollama", "openai", "local_onnx"]
    model: str
    dimension: int = Field(..., ge=1, le=8192)
    endpoint_override: str | None = None
    api_key: str | None = None


class HotModelSwitchResponse(_Loose):
    job_id: str
    status: str


class JobProgress(_Loose):
    chunks_done: int = 0
    chunks_total: int = 0


class Job(_Loose):
    job_id: str
    kind: str
    tenant_id: str | None = None
    index_id: str | None = None
    status: str
    progress: JobProgress | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    error: str | None = None


class JobList(_Loose):
    jobs: list[Job] = Field(default_factory=list)
    total: int = 0
    next_cursor: str | None = None


# ---------------------------------------------------------------------------
# Cluster
# ---------------------------------------------------------------------------


class ClusterNode(_Loose):
    id: str
    addr: str | None = None
    zone: str | None = None
    state: str | None = None
    last_seen: datetime | None = None


class ClusterNodeList(_Loose):
    nodes: list[ClusterNode] = Field(default_factory=list)
    leader: str = ""


class ClusterShard(_Loose):
    id: str
    primary: str | None = None
    replicas: list[str] = Field(default_factory=list)
    zone_placement: dict[str, str] | None = None


class ClusterShardList(_Loose):
    shards: list[ClusterShard] = Field(default_factory=list)
    rf: int = 0


class ClusterHealth(_Loose):
    status: str
    cluster_size: int = 0
    alive_nodes: int = 0
    raft_has_leader: bool = False
    under_replicated_shards: int = 0


# ---------------------------------------------------------------------------
# Org-level
# ---------------------------------------------------------------------------


class OrgSyncDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str | None = None
    text: str
    metadata: dict[str, str] | None = None


class OrgSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    source_type: str
    shared: bool
    documents: list[OrgSyncDocument]


class OrgSyncResponse(_Loose):
    synced: int
    org_id: str
    user_id: str
    source_type: str
    index_type: str


class MultiSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    k: int | None = None
    sources: list[str] | None = None
    ef_search: int | None = None
    include_text: bool | None = None
    start_time: int | None = None
    end_time: int | None = None
    distance_threshold: float | None = None


class MultiSearchResult(_Loose):
    chunk_id: int
    text: str | None = None
    distance: float = 0.0
    source_type: str | None = None
    repo_id: str | None = None
    created_at: int | None = None
    shared: bool | None = None
    metadata: dict[str, Any] | None = None


class MultiSearchResponse(_Loose):
    results: list[MultiSearchResult] = Field(default_factory=list)
    total: int = 0
    query: str | None = None
    org_id: str | None = None
    user_id: str | None = None


class OrgIndexEntry(_Loose):
    id: str
    name: str | None = None
    status: str | None = None
    num_chunks: int | None = None


class OrgIndexList(_Loose):
    indexes: list[OrgIndexEntry] = Field(default_factory=list)
    total: int = 0
    org_id: str | None = None
    user_id: str | None = None


# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------


class LLMSettings(BaseModel):
    """LLM settings stored on a tenant.

    The server masks the API key on read responses (``***xxxx``); send the
    full key on writes — the server preserves the existing key when a
    masked value is sent back.
    """

    model_config = ConfigDict(extra="allow")

    provider: Literal["openai", "ollama", "anthropic"] | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class LLMSettingsResponse(_Loose):
    """Response envelope used by the update endpoint."""

    message: str | None = None
    org_id: str | None = None
    settings: LLMSettings | None = None


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


class CreateApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    description: str | None = None


class ApiKey(_Loose):
    id: str
    description: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked: bool | None = None
    # Plaintext key — only ever returned by ``create_api_key``. Persist it
    # client-side; the server cannot reveal it again.
    key: str | None = None


class ApiKeyList(_Loose):
    keys: list[ApiKey] = Field(default_factory=list)
    total: int = 0
