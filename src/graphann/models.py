"""Pydantic v2 models for every GraphANN request and response shape.

The models accept extra fields (``model_config = {"extra": "allow"}``) so
forward-compatible server changes do not break existing clients. Outbound
request bodies are strict — ``model_dump(exclude_none=True)`` is used by
the HTTP layer so optional knobs default to whatever the server picks.

Most classes here are hand-written for ergonomics (stable names, tolerant
parsing, docstrings) and are kept in sync with ``_generated.py`` by hand
when the spec drifts. The models for the backup / batch-search / license /
embed-space-admin endpoints have no pre-existing hand-written counterpart
(those endpoints were previously unreachable from this SDK), so they are
re-exported directly from the spec-generated module instead of being
duplicated by hand -- see ``_generated.py`` for their field definitions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ._generated import BackupChunkInfo as BackupChunkInfo
from ._generated import BackupManifest as BackupManifest
from ._generated import BackupMeta as BackupMeta
from ._generated import BackupSummary as BackupSummary
from ._generated import BatchSearchRequest as BatchSearchRequest
from ._generated import BatchSearchResponse as BatchSearchResponse
from ._generated import BatchSearchResult as BatchSearchResult
from ._generated import CompactAllResponse as CompactAllResponse
from ._generated import CompactAllSkipped as CompactAllSkipped
from ._generated import CreateBackupResponse as CreateBackupResponse
from ._generated import DeleteBackupResponse as DeleteBackupResponse
from ._generated import EmbedSpaceAdminResponse as EmbedSpaceAdminResponse
from ._generated import EmbedSpaceIndexRow as EmbedSpaceIndexRow
from ._generated import LicenseAuditEvent as LicenseAuditEvent
from ._generated import LicenseEntitlements as LicenseEntitlements
from ._generated import LicenseStatus as LicenseStatus
from ._generated import ListBackupsResponse as ListBackupsResponse
from ._generated import RestoreBackupRequest as RestoreBackupRequest
from ._generated import RestoreBackupResponse as RestoreBackupResponse

__all__ = [
    "AddDocumentsResponse",
    "ApiKey",
    "ApiKeyList",
    "BackupChunkInfo",
    "BackupManifest",
    "BackupMeta",
    "BackupSummary",
    "BatchSearchRequest",
    "BatchSearchResponse",
    "BatchSearchResult",
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
    "CompactAllResponse",
    "CompactAllSkipped",
    "CreateApiKeyRequest",
    "CreateBackupResponse",
    "CreateIndexRequest",
    "CreateTenantRequest",
    "DeleteBackupResponse",
    "DeleteChunksResponse",
    "Document",
    "DocumentInput",
    "DocumentListEntry",
    "DocumentListPage",
    "EmbedSpaceAdminResponse",
    "EmbedSpaceIndexRow",
    "FlushResponse",
    "GCResponse",
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
    "LicenseAuditEvent",
    "LicenseEntitlements",
    "LicenseStatus",
    "ListBackupsResponse",
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
    "RebuildGraphResponse",
    "RestoreBackupRequest",
    "RestoreBackupResponse",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "Tenant",
    "TenantList",
    "UpdateIndexRequest",
    "UpsertResourceRequest",
    "UpsertResourceResponse",
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


IndexStatusValue = Literal["pending", "building", "ready", "error", "deleted"]


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
    # Compression strategy configured for this index (e.g. "scalar", "pq").
    compression: str | None = None
    # Whether approximate (HNSW) search is enabled.
    approximate: bool | None = None


class IndexList(_Loose):
    indexes: list[Index] = Field(default_factory=list)
    total: int = 0


class CreateIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    id: str | None = None
    # Optional compression strategy: "scalar", "binary", "pq", "recompute", or "".
    compression: str | None = None
    # Optional: enable approximate (HNSW) search. None defers to server default.
    approximate: bool | None = None


class UpdateIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    # Optional compression strategy update.
    compression: str | None = None
    # Optional approximate-search flag update.
    approximate: bool | None = None
    # Per-index embedding backend override. Remote backends only ("" |
    # "ollama" | "openai"); "" clears the override back to the
    # process-wide embedder.
    embedding_backend: str | None = None
    embedding_model: str | None = None
    # SSRF-validated at PATCH time (public http/https hosts only).
    embedding_endpoint: str | None = None
    embedding_dimension: int | None = None
    # ENV VAR NAME holding the backend key -- never the key itself.
    embedding_api_key_env: str | None = None


class IndexStatus(_Loose):
    index_id: str
    status: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentInput(BaseModel):
    """A document to ingest into an index.

    Either ``text`` or ``content`` is accepted by the server -- ``content``
    is an alias for ``text``; if both are set, ``text`` takes precedence.
    Supply at least one. ``id`` becomes the document's external ID.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    # Was required; the server accepts ``content`` alone (see below), so
    # this is now optional to match. Breaking change: callers that always
    # passed ``text`` are unaffected, but static type checkers no longer
    # require it.
    text: str | None = None
    # Alias for ``text``. If both are set, ``text`` wins server-side.
    content: str | None = None
    metadata: dict[str, Any] | None = None
    upsert: bool = False
    expires_at: datetime | None = None
    repo_id: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    # Precomputed embedding vector. When EVERY document in a batch carries
    # a vector the server skips embedding entirely (precomputed-ingest
    # path); a MIXED batch — some with, some without — is rejected with
    # HTTP 400. Vector length must match the index dimension once it is
    # set (a fresh index accepts any length; first ingest fixes it).
    vector: list[float] | None = None
    # Same embedding as ``vector``, base64-encoded little-endian float32.
    # Cheaper to decode for bulk loads. Set one or the other, never both.
    vector_b64: str | None = None


class AddDocumentsResponse(_Loose):
    added: int
    index_id: str
    # Server emits []store.ChunkID (= []string), not integers.
    chunk_ids: list[str] = Field(default_factory=list)
    # Present only when the server minted at least one external ID
    # (sharded ingest of id-less documents — the external ID is the shard
    # routing key). One entry per submitted document, positionally aligned
    # with the request array; persist these as the durable document IDs.
    # ``None`` on unsharded deployments and when every document supplied
    # its own ``id``.
    external_ids: list[str] | None = None


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
    # Generic metadata pre-filter: every key/value pair must match (string equality).
    equals: dict[str, str] | None = None
    # Drops chunk text from every result. At k=10, text is ~75% of the
    # response body; skipping it also skips the per-result zstd
    # decompression of the chunk text store. Off by default.
    omit_text: bool | None = None


class SearchRequest(BaseModel):
    """Body for ``POST /search``.

    The ``rerank``/``candidate_k``/``rerank_k`` fields opt in to
    cross-encoder reranking when the server has a reranker configured
    (via ``--reranker-url``). Silently no-ops on servers without one.
    """

    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    vector: list[float] | None = None
    k: int | None = None
    filter: SearchFilter | None = None

    # Cross-encoder reranker controls. Effective only when the server has
    # a reranker configured AND ``rerank`` is True. Vector-only requests
    # ignore ``rerank`` (no text query to feed the cross-encoder).
    rerank: bool | None = None
    candidate_k: int | None = None  # default max(4*k, 50); server clamps to [k, 1000]
    rerank_k: int | None = None  # default = k

    # Per-query HNSW beam width. 0 / omitted = server default (the
    # ``--search-ef`` flag, default 64). The server clamps rather than
    # rejects: negative values fall back to the default, values above
    # 2000 are capped. Binary / PQ flat-scan modes ignore it entirely.
    ef_search: int | None = None

    # Query vector as base64-encoded little-endian float32 -- cheaper to
    # decode than ``vector`` (query JSON decoding measured at 17.5% of
    # server CPU under load). Mutually exclusive with ``vector``: set one
    # or the other, never both.
    vector_b64: str | None = None

    # Fuses dense (semantic) results with a BM25 lexical ranking via
    # Reciprocal Rank Fusion. Text-query searches only; ignored for
    # vector-only requests. Falls back to dense-only if the lexical
    # index can't be built. Default False preserves prior behavior.
    hybrid: bool | None = None


class SearchResult(_Loose):
    """One hit in a search response.

    ``score`` is always the first-stage cosine similarity (higher is
    better). ``rerank_score`` is populated only when the server
    actually applied the cross-encoder reranker — it carries the
    reranker's native relevance score (different scale from cosine,
    typically -10..10 for bge-reranker-v2-m3). When ``rerank_score``
    is set, the result ordering reflects it; when ``None``, ordering
    is by ``score``.
    """

    id: str
    text: str | None = None
    score: float = 0.0
    rerank_score: float | None = None
    metadata: Any = None


class SearchResponse(_Loose):
    """Search response envelope.

    The ``partial`` / ``shards_total`` / ``shards_ok`` /
    ``degraded_shards`` fields are emitted only on the sharded
    scatter-gather path (cluster deployments where the index has more
    than one shard) — they are ``None`` everywhere else. ``partial`` is
    ``True`` when at least one shard contributed nothing.
    ``degraded_shards`` lists the failing shard IDs and is present only
    when non-empty. ``rerank_applied`` reports whether the server applied
    cross-encoder reranking, including coordinator-side sharded reranking.
    """

    results: list[SearchResult] = Field(default_factory=list)
    total: int = 0
    partial: bool | None = None
    shards_total: int | None = None
    shards_ok: int | None = None
    degraded_shards: list[str] | None = None
    rerank_applied: bool | None = None


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


class FlushResponse(_Loose):
    """Body returned by ``POST .../indexes/{id}/flush``."""

    flushed: bool = False


class RebuildGraphResponse(_Loose):
    """Body returned by ``POST .../indexes/{id}/rebuild-graph``."""

    rebuilt: bool = False
    chunks: int = 0
    wall_ms: int = 0


class ProcessPendingResponse(_Loose):
    index_id: str
    processed: int
    chunks_created: int
    # Server emits []store.ChunkID (= []string), not integers.
    chunk_ids: list[str] = Field(default_factory=list)


class CleanupOrphansResponse(_Loose):
    """Body returned by ``POST /v1/admin/cleanup-orphans``.

    ``min_age`` is a Go-style duration string echoing the cutoff the
    server actually applied (e.g. ``"1h0m0s"``, ``"24h0m0s"``).
    ``dry_run`` echoes the dry-run flag — when ``True``, ``removed`` is
    what would have been deleted, not what was deleted.
    """

    removed: list[str] = Field(default_factory=list)
    freed_bytes: int = 0
    min_age: str = ""
    dry_run: bool = False


class GCResponse(_Loose):
    """Body returned by both ``POST .../indexes/{id}/gc`` and
    ``POST /v1/admin/gc``. Reports the count of expired documents reclaimed."""

    index_id: str = ""
    deleted_count: int = 0


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
    """Body for ``POST /v1/tenants/{tid}/api-keys``.

    Both fields are sent. ``user_id`` may be empty (scopes the key to the
    tenant rather than a specific user); ``name`` is the key's label.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = ""
    name: str = ""


class ApiKey(_Loose):
    """API key resource.

    ``plaintext`` is only ever populated by ``create_api_key`` — the
    server returns the one-time secret once and cannot reveal it again.
    List responses leave it ``None``.
    """

    id: str
    name: str | None = None
    user_id: str | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    # One-time plaintext secret. Returned only by ``create_api_key``;
    # persist it client-side immediately.
    plaintext: str | None = None


class ApiKeyList(_Loose):
    api_keys: list[ApiKey] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resource upsert
# ---------------------------------------------------------------------------


class UpsertResourceRequest(BaseModel):
    """Body for ``PUT /v1/tenants/{tid}/indexes/{iid}/resources/{resID}``."""

    model_config = ConfigDict(extra="forbid")

    text: str
    metadata: dict[str, str] | None = None
    # Optional stable external ID (e.g. document UUID), passed through to
    # chunk metadata. Distinct from the path ``resource_id``.
    external_id: str | None = None
    repo_id: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    source_type: str | None = None
    owner_user_id: str | None = None
    title: str | None = None
    url: str | None = None


class UpsertResourceResponse(_Loose):
    """Response from ``PUT .../resources/{resID}``."""

    resource_id: str
    chunks_added: int
    chunks_tombstoned: int
    # "create" on first upsert, "update" on subsequent ones.
    operation: str
