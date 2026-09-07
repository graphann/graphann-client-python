# GENERATED FILE -- DO NOT HAND-EDIT.
#
# Source:  api/openapi/spec.yaml
# Command: datamodel-codegen --input <spec.yaml> --input-file-type openapi \
#            --output src/graphann/_generated.py --target-python-version 3.10 \
#            --formatters black --disable-timestamp --field-constraints \
#            --custom-file-header-path scripts/_generated_header.txt
# Regenerate from the SDK root via: scripts/generate_types.sh
# Staleness is enforced by tests/test_generated_staleness.py -- it fails the
# suite if this file no longer matches what the generator currently produces.
#
# Any hand edit made to this file will be silently discarded on the next
# regeneration. Add ergonomics/aliases in models.py instead.

from __future__ import annotations

from enum import Enum
from typing import Any, Dict

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Code(Enum):
    internal_error = "internal_error"
    bad_request = "bad_request"
    unauthorized = "unauthorized"
    forbidden = "forbidden"
    not_found = "not_found"
    conflict = "conflict"
    quota_exceeded = "quota_exceeded"
    rate_limited = "rate_limited"
    validation_error = "validation_error"
    index_not_ready = "index_not_ready"
    index_building = "index_building"
    service_unavailable = "service_unavailable"
    payload_too_large = "payload_too_large"
    not_implemented = "not_implemented"


class APIError(BaseModel):
    code: Code = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error message.")
    details: Any | None = Field(
        None, description="Optional structured details about the error."
    )


class Status(Enum):
    healthy = "healthy"


class HealthResponse(BaseModel):
    status: Status | None = None


class Status1(Enum):
    ready = "ready"
    not_ready = "not ready"


class ReadyResponse(BaseModel):
    status: Status1 | None = None
    reason: str | None = Field(None, description="Reason when not ready.")


class CreateTenantRequest(BaseModel):
    id: str | None = Field(
        None,
        description="Optional custom tenant ID for deterministic creation (idempotent).",
    )
    name: str = Field(..., description="Human-readable tenant name.")


class TenantResponse(BaseModel):
    id: str | None = None
    name: str | None = None
    created_at: AwareDatetime | None = None


class TenantDetailResponse(BaseModel):
    id: str | None = None
    name: str | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None


class TenantListEntry(BaseModel):
    id: str | None = None
    name: str | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    index_count: int | None = Field(
        None,
        description="Number of indexes owned by this tenant. Best-effort: a failed\nlookup reports 0 for that tenant rather than failing the listing.\n",
    )
    metadata: dict[str, str] | None = Field(
        None,
        description="Operator-set tenant metadata, with any embedded credentials\nmasked. Absent when the tenant has none.\n",
    )


class ListTenantsResponse(BaseModel):
    tenants: list[TenantListEntry] | None = None
    total: int | None = None


class Compression(Enum):
    field_ = ""
    scalar = "scalar"
    binary = "binary"
    pq = "pq"
    recompute = "recompute"


class CreateIndexRequest(BaseModel):
    id: str | None = Field(
        None,
        description="Optional custom index ID for deterministic creation (idempotent).",
    )
    name: str = Field(..., description="Human-readable index name.")
    description: str | None = Field(None, description="Optional description.")
    compression: Compression | None = Field(
        None,
        description="Compression mode for the new index. Optional; when omitted the\nserver's `--default-compression` value is used. Once set,\ncontrols the on-disk format produced by every subsequent\ncompaction. To change mode after creation use the offline\n`graphann recompact` CLI tool.\n",
    )
    approximate: bool | None = Field(
        None,
        description='If true, skip the exact rerank step during PQ-mode search\n(TwoLevelSearcher.RerankRatio = 0). Recall drops ~1-2%;\nlatency drops 10-50x on the rerank-bound path. No-op for\nnon-PQ compression modes (`recompute`, `none`, `scalar`,\n`binary`) — those have no rerank step to skip. Defaults to\nfalse. See `docs/COMPRESSION.md` § "Approximate-only mode".\n',
    )


class EmbeddingBackend(Enum):
    field_ = ""
    ollama = "ollama"
    openai = "openai"


class UpdateIndexRequest(BaseModel):
    name: str | None = Field(None, description="New index name.")
    description: str | None = Field(None, description="New description.")
    approximate: bool | None = Field(
        None,
        description="When true, enables approximate-only PQ-mode search: the exact\nrerank step is skipped (TwoLevelSearcher.RerankRatio = 0).\nRecall drops ~1-2%; latency drops 10-50x on the rerank-bound\npath. No-op for non-PQ compression modes. Change propagates to\na loaded LiveIndex immediately — no restart required.\n",
    )
    compression: Compression | None = Field(
        None,
        description="Advisory compression preference for the next compaction. Updating\nthis field does NOT migrate existing on-disk data — it only sets\nthe mode that LiveIndex.Compact will use the next time it runs.\nTo migrate existing data immediately, run `graphann recompact`\noffline or trigger a manual compaction.\n",
    )
    embedding_backend: EmbeddingBackend | None = Field(
        None,
        description='Per-index embedding backend override. Remote backends only --\nper-index local_onnx instances are deliberately unsupported;\nuse the process embedder for local models. Setting this to ""\nclears the override back to the process-wide embedder.\n',
    )
    embedding_model: str | None = Field(
        None,
        description='Backend model identifier (e.g. "text-embedding-3-small",\n"intfloat/multilingual-e5-small"). e5-family models get the\nquery:/passage: intent prefixes applied automatically by the\nopenai backend preset.\n',
    )
    embedding_endpoint: str | None = Field(
        None,
        description="Optional override of the backend base URL. SSRF-validated at\nPATCH time (public http/https hosts only) and re-guarded at\nconnect time, so it cannot point at loopback/RFC1918/metadata\nranges.\n",
    )
    embedding_dimension: int | None = Field(
        None,
        description="Expected output dimension for the per-index embedding override.",
    )
    embedding_api_key_env: str | None = Field(
        None,
        description="ENV VAR NAME holding the backend key -- never send the key\nitself in this field.\n",
    )


class Status2(Enum):
    pending = "pending"
    building = "building"
    ready = "ready"
    error = "error"
    deleted = "deleted"


class IndexInfo(BaseModel):
    id: str | None = None
    tenant_id: str | None = None
    name: str | None = None
    description: str | None = None
    status: Status2 | None = None
    error: str | None = None
    num_docs: int | None = None
    num_chunks: int | None = None
    dimension: int | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    last_compacted_at: AwareDatetime | None = Field(
        None,
        description="Wall-clock time of the most recent successful compaction.\nAbsent when the index has never been compacted (either\ngenuinely fresh, or compacted before this field existed --\ncallers fall back to `created_at` in that case).\n",
    )
    created_by: str | None = Field(
        None, description="User ID of the index's creator, if known."
    )
    path: str | None = Field(
        None, description="On-disk directory the index is stored under."
    )
    metadata: dict[str, str] | None = Field(
        None, description="Arbitrary operator-set key/value metadata for this index."
    )
    compression: Compression | None = Field(
        None,
        description="Currently configured compression mode. Reflects the value set at\ncreation time (or the server default when the request omitted it).\nEmpty string indicates a legacy index that predates this field; it\nwill adopt the server default at the next compaction.\n",
    )
    approximate: bool | None = Field(
        None,
        description="True when this index is in approximate-only mode: PQ-mode search\nskips the exact rerank step. See `CreateIndexRequest.approximate`\nfor the full contract. Always false for non-PQ indexes.\n",
    )
    vectors_external: bool | None = Field(
        None,
        description="True once the index has ingested at least one client-supplied\n(precomputed) vector -- meaning the stored vectors/codes live\nin the CLIENT's embedding space, not the server embedder's.\nOnce set, compacted search paths rank candidates in the\nindex's own code space and never re-embed candidate texts for\nreranking.\n",
    )
    embedding_backend: str | None = Field(
        None,
        description="Per-index embedding backend override, if configured. Empty\nfor the default (process-wide embedder). See\n`UpdateIndexRequest.embedding_backend`.\n",
    )
    embedding_model: str | None = Field(
        None,
        description="Per-index embedding model identifier, if `embedding_backend` is set.",
    )
    embedding_endpoint: str | None = Field(
        None, description="Per-index embedding backend base URL override, if set."
    )
    embedding_dimension: int | None = Field(
        None,
        description="Expected output dimension for the per-index embedding override, if set.",
    )
    embedding_api_key_env: str | None = Field(
        None,
        description="ENV VAR NAME holding the per-index embedding backend key, if set.",
    )


class EmbedSpaceState(Enum):
    unknown = "unknown"
    verified = "verified"
    mismatch = "mismatch"
    external_unverified = "external_unverified"
    external_agree = "external_agree"
    external_diverged = "external_diverged"


class EmbedSpacePolicy(Enum):
    warn = "warn"
    refuse_search = "refuse_search"
    refuse_open = "refuse_open"


class IndexStatusResponse(BaseModel):
    index_id: str | None = None
    status: Status2 | None = None
    error: str | None = None
    embed_space_state: EmbedSpaceState | None = Field(
        None, description="Embedding-space classification of this index."
    )
    embed_fingerprint: str | None = Field(
        None, description="The index's own stored embedding fingerprint."
    )
    server_embed_fingerprint: str | None = Field(
        None,
        description="Fingerprint of the embedder this server is currently serving with.",
    )
    embed_space_policy: EmbedSpacePolicy | None = Field(
        None,
        description="Mismatch policy in force for THIS index, i.e. the global policy\nafter any per-index allow-list override.\n",
    )
    embed_space_detail: str | None = Field(
        None,
        description="Human-readable detail for the state. Empty string when there is none.",
    )
    embed_space_checked_at: AwareDatetime | None = Field(
        None, description="When the state was last resolved. Absent if never checked."
    )


class ListIndexesResponse(BaseModel):
    indexes: list[IndexInfo] | None = None
    total: int | None = None


class Document(BaseModel):
    id: str | None = Field(None, description="Optional custom document ID.")
    text: str | None = Field(None, description="Document text content.")
    content: str | None = Field(
        None,
        description="Alias for `text`. If both are provided, `text` takes precedence.",
    )
    metadata: Any | None = Field(
        None, description="Arbitrary metadata attached to the document."
    )
    repo_id: str | None = Field(None, description="Repository ID for RBAC filtering.")
    file_path: str | None = Field(None, description="File path within the repository.")
    commit_sha: str | None = Field(None, description="Git commit SHA.")
    upsert: bool | None = Field(
        None,
        description="When true, existing chunks with the same external ID are\ndeleted before this document is queued, making ingest\nidempotent by key. Replaces the semantic\nDeleteByQuery-then-Import pattern for clients that want\nreplace-on-reimport semantics.\n",
    )
    expires_at: AwareDatetime | None = Field(
        None,
        description="Optional RFC3339 timestamp after which this document's\nchunks are hidden from search and eligible for GC. Absent\nmeans never.\n",
    )
    vector: list[float] | None = Field(
        None,
        description="Optional precomputed embedding. When every document in the\nrequest carries a vector, ingest skips internal embedding\nand inserts the vectors directly.\n",
    )
    vector_b64: str | None = Field(
        None,
        description="The same embedding as `vector`, base64-encoded little-endian\nfloat32 (numpy `astype('<f4').tobytes()` /\n`binary.LittleEndian`). An alternative to `vector` for bulk\nloads that is cheaper to decode. Set one or the other, never\nboth.\n",
    )


class UpsertResourceRequest(BaseModel):
    text: str = Field(..., description="Full text content for this resource version.")
    external_id: str | None = Field(
        None,
        description="Optional stable external ID (e.g. document UUID). Passed through to chunk metadata.",
    )
    metadata: dict[str, str] | None = Field(
        None, description="Optional key/value metadata attached to all chunks."
    )
    repo_id: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    source_type: str | None = None
    owner_user_id: str | None = None
    title: str | None = None
    url: str | None = None


class Operation(Enum):
    create = "create"
    update = "update"


class UpsertResourceResponse(BaseModel):
    resource_id: str | None = Field(
        None, description="The resource ID that was upserted."
    )
    index_id: str | None = None
    chunks_added: int | None = Field(None, description="Number of new chunks created.")
    chunks_tombstoned: int | None = Field(
        None,
        description="Number of previously-live chunks now tombstoned (reclaimed at next compaction).",
    )
    operation: Operation | None = Field(
        None,
        description="`create` when no prior chunks existed; `update` when old chunks were tombstoned.",
    )


class AddDocumentsRequest(BaseModel):
    documents: list[Document] = Field(..., min_length=1)
    defer_save: bool | None = Field(
        False,
        description="Skips the per-batch full-delta save during a bulk load: data\nstays in memory (index marked dirty) and is persisted once\nthe caller POSTs to `.../flush`. Avoids an O(N^2) full-delta\nre-save on every ingest request. Also settable via the\n`?defer_save=true` query param. Default false preserves the\nper-batch save behavior.\n",
    )
    bulk: bool | None = Field(
        False,
        description="Enables bulk-ingest mode: in addition to deferring the\nper-batch save (`bulk` implies `defer_save`), the per-node\nHNSW graph insert is deferred and the delta graph is built\nonce, concurrently, when the caller POSTs to `.../flush`.\nThe fast path for large loads. IMPORTANT: bulk-ingested data\nis NOT searchable until `.../flush` builds the graph. Also\nsettable via the `?bulk=true` query param. Default false\npreserves the immediately-searchable per-node insert\nbehavior.\n",
    )


class AddDocumentsResponse(BaseModel):
    added: int | None = Field(None, description="Number of documents added.")
    index_id: str | None = None
    chunk_ids: list[str] | None = Field(
        None,
        description="IDs of created chunks. These are store.ChunkID values, which are\nSTRINGS -- earlier revisions of this document typed them as\nintegers, which no server has ever sent.\n",
    )
    external_ids: list[str] | None = Field(
        None,
        description="Present only when the server minted external IDs during this\ningest. A sharded index requires an external ID per document (it\nis the routing key), so documents that arrive without one are\ngiven one; this returns the durable IDs. Absent entirely for\nunsharded ingests and for sharded ingests where the client\nsupplied every ID.\n",
    )


class GetDocumentChunk(BaseModel):
    chunk_id: int | None = None
    uuid: str | None = None
    text: str | None = None
    chunk_index: int | None = None
    start: int | None = Field(
        None, description="Start byte offset in the original document."
    )
    end: int | None = Field(
        None, description="End byte offset in the original document."
    )
    repo_id: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None


class GetDocumentResponse(BaseModel):
    index_id: str | None = None
    document_id: int | None = None
    external_id: str | None = Field(
        None,
        description="Taken from the first chunk; every chunk of a document shares it.",
    )
    chunks: list[GetDocumentChunk] | None = None
    total_chunks: int | None = None


class DeleteDocumentResponse(BaseModel):
    deleted_chunks: int | None = None
    document_id: int | None = None
    index_id: str | None = None


class BulkDeleteDocumentsRequest(BaseModel):
    document_ids: list[int] = Field(..., min_length=1)


class BulkDeleteDocumentsResponse(BaseModel):
    index_id: str | None = None
    documents_deleted: int | None = None
    chunks_deleted: int | None = None
    deleted_per_doc: dict[str, int] | None = Field(
        None, description="Map of document ID to number of chunks deleted."
    )


class BulkDeleteByExternalIDsRequest(BaseModel):
    external_ids: list[str] = Field(
        ..., description="Client-provided external IDs to delete.", min_length=1
    )


class BulkDeleteByExternalIDsResponse(BaseModel):
    index_id: str | None = None
    documents_deleted: int | None = None
    chunks_deleted: int | None = None
    deleted_per_id: dict[str, int] | None = Field(
        None, description="Map of external ID to number of chunks deleted."
    )


class ChunkResponse(BaseModel):
    chunk_id: int | None = None
    text: str | None = None
    document_id: int | None = None
    chunk_index: int | None = None
    start: int | None = Field(
        None, description="Start byte offset in the original document."
    )
    end: int | None = Field(
        None, description="End byte offset in the original document."
    )


class DeleteChunksRequest(BaseModel):
    chunk_ids: list[int] = Field(..., min_length=1)


class DeleteChunksResponse(BaseModel):
    deleted: int | None = None
    index_id: str | None = None


class SearchFilter(BaseModel):
    repo_ids: list[str] | None = Field(
        None,
        description="Filter results to only include chunks from these repository IDs.\nIf empty, no filtering is applied.\n",
    )
    equals: dict[str, str] | None = Field(
        None,
        description='Generic field-equality filter over ChunkMetadata fields. Every\nentry must match for a chunk to pass (AND semantics). An empty\nor absent map matches all chunks. An unknown key excludes all\nchunks (defensive default).\n\nSupported keys: author, author_email, title, url, content_type,\ncontent_id, thread_id, source_type, source_id, source_name,\nconnector_id, repo_id, file_path, commit_sha, owner_user_id,\nresource_id, external_id, shared ("true"/"false"),\ndocument_id (decimal string).\n',
        examples=[{"author": "alice", "content_type": "email"}],
    )
    omit_text: bool | None = Field(
        False,
        description="Drops the chunk text from every result. Off by default, so\nan existing client sees exactly what it saw before. Worth\nsetting for a caller that already holds the text -- a RAG\npipeline reading from its own store, or a reranking stage\nkeyed on ids. At k=10, text is 75% of the response body;\nskipping it also skips the per-result zstd decompression of\nthe chunk text store, not just the bytes on the wire.\n",
    )
    exclude_external_ids: list[str] | None = Field(
        None,
        description='Removes chunks whose external ID is in this list. Use case:\nstrip well-known synthetic docs (e.g. "__seed__") from\nresults.\n',
    )
    metadata_filter: dict[str, Any] | None = Field(
        None,
        description="Requires each key/value to match the chunk's sidecar\nmetadata exactly. Keys absent from the chunk's sidecar fail\nthe filter. Empty/absent map disables this filter.\n",
    )


class SearchRequest(BaseModel):
    query: str | None = Field(None, description="Text query for semantic search.")
    vector: list[float] | None = Field(
        None,
        description="Raw embedding vector for nearest-neighbor search. Mutually\nexclusive with `vector_b64` -- set one or the other, never\nboth.\n",
    )
    vector_b64: str | None = Field(
        None,
        description="The query vector as base64-encoded little-endian float32,\nthe same encoding accepted on ingest -- an alternative to\n`vector` that is cheaper to decode (query JSON decoding\nmeasured at 17.5% of server CPU under load). Mutually\nexclusive with `vector` -- set one or the other, never both.\n",
    )
    k: int | None = Field(10, description="Maximum number of results to return.")
    filter: SearchFilter | None = None
    rerank: bool | None = Field(
        False,
        description="When true, rescore the top-`candidate_k` HNSW candidates with the\nserver-configured cross-encoder reranker and return the top-`rerank_k`\n(or top-`k` if `rerank_k` is unset) by reranker score. Silently no-op\nwhen the server has no reranker configured (`--reranker-url` unset),\nso flipping this on a non-rerank-aware deployment is safe.\n\nReranking only applies to the text-`query` path. Vector-only\nrequests ignore this flag (no text query to feed the cross-encoder).\n",
    )
    candidate_k: int | None = Field(
        None,
        description="Size of the first-stage candidate pool fed to the reranker. Effective\nonly when `rerank=true`. Defaults to `max(4*k, 50)`. Server clamps to\n`[k, 1000]`.\n",
    )
    rerank_k: int | None = Field(
        None,
        description="Number of results to return AFTER reranking. Effective only when\n`rerank=true`. Defaults to `k`.\n",
    )
    ef_search: int | None = Field(
        None,
        description="Per-query HNSW search breadth (candidate list size). 0 (the\ndefault) uses the server default. Clamped to a maximum of\n2000.\n",
    )
    hybrid: bool | None = Field(
        False,
        description="Fuses the dense (semantic) results with a BM25 lexical\nranking via Reciprocal Rank Fusion (RRF), so rare-token /\nkeyword matches surface alongside semantic ones. Applies to\ntext `query` searches only -- ignored for vector-only\nrequests. Default false = dense-only. Safe to flip: falls\nback to dense-only results if the lexical index can't be\nbuilt.\n",
    )


class Metadata(BaseModel):
    model_config = ConfigDict(
        extra="allow",
    )
    __annotations__ = {
        "__pydantic_extra__": Dict[str, Any],
    }
    document_id: int | None = Field(None, description="Internal document ID.")
    chunk_index: int | None = Field(
        None, description="Chunk index within the document."
    )
    repo_id: str | None = Field(None, description="Repository ID for RBAC filtering.")
    file_path: str | None = Field(None, description="File path within the repository.")
    commit_sha: str | None = Field(None, description="Git commit SHA.")


class SearchResult(BaseModel):
    id: str | None = Field(
        None,
        description="Document identifier. Returns the client-provided external ID\nwhen available, otherwise falls back to the integer chunk index\nformatted as a string.\n",
    )
    text: str | None = None
    score: float | None = Field(
        None,
        description="First-stage cosine similarity (higher is better). Always\npopulated, regardless of whether reranking ran. Clients can\nrely on this single scale across rerank and non-rerank\nrequests.\n",
    )
    rerank_score: float | None = Field(
        None,
        description="Cross-encoder relevance score, in the reranker's native\nscale (typically roughly -10 to 10 for bge-reranker-v2-m3).\nPresent only when the request set `rerank=true` AND the\nserver applied the reranker successfully. Absent when the\nserver has no reranker, the request didn't ask for rerank,\nor the reranker errored and the server fell back to\nfirst-stage results. Clients that want the post-rerank\norder should sort by `rerank_score` when present and fall\nback to `score` otherwise.\n",
    )
    metadata: Metadata | None = Field(
        None, description="Chunk metadata merged with arbitrary user metadata."
    )


class SearchResponse(BaseModel):
    results: list[SearchResult] | None = None
    total: int | None = None
    partial: bool | None = Field(
        None, description="Whether one or more shards did not return complete results."
    )
    shards_total: int | None = Field(
        None, description="Total shards targeted by a sharded search."
    )
    shards_ok: int | None = Field(
        None, description="Shards that returned complete results."
    )
    degraded_shards: list[str] | None = Field(
        None, description="Identifiers of degraded shards, when present."
    )
    rerank_applied: bool | None = Field(
        None,
        description="Whether the server applied reranking. May be absent on older servers or when reranking was not requested.",
    )


class Status4(Enum):
    compacting = "compacting"


class CompactResponse(BaseModel):
    index_id: str | None = None
    status: Status4 | None = Field(
        None,
        description="Always `compacting`, never `compacted`: compaction runs in the\nbackground and nothing has been merged when this returns. Track\ncompletion via GET /v1/jobs.\n",
    )
    message: str | None = None


class Status5(Enum):
    cleared = "cleared"


class ClearResponse(BaseModel):
    index_id: str | None = None
    status: Status5 | None = None
    message: str | None = None


class LiveStatsResponse(BaseModel):
    index_id: str | None = None
    is_live: bool | None = Field(
        None, description="Whether the index is currently loaded in memory."
    )
    dimension: int | None = Field(
        None,
        description="Embedding dimension (present in both live and non-live responses).",
    )
    base_chunks: int | None = Field(
        None, description="Number of chunks in the compacted base graph."
    )
    delta_chunks: int | None = Field(
        None, description="Number of chunks in the uncompacted delta layer."
    )
    frozen_chunks: int | None = Field(
        None,
        description="Chunks rotated out of the active delta and not yet folded into the new base by an in-flight compaction (delta-A). Already counted in total_chunks/live_chunks so those totals don't visibly drop during a compaction window; reported separately so delta_chunks keeps its established meaning (active delta-B only). Always 0 in the not-loaded fallback.",
    )
    total_chunks: int | None = Field(None, description="Total chunks (base + delta).")
    deleted_chunks: int | None = Field(None, description="Number of deleted chunks.")
    live_chunks: int | None = Field(
        None, description="Active chunks (total - deleted)."
    )
    documents: int | None = Field(None, description="Number of documents.")
    is_dirty: bool | None = Field(
        None, description="Whether the delta layer has uncompacted changes."
    )
    base_bytes: int | None = Field(
        None, description="On-disk size of the compacted base index directory."
    )
    delta_bytes: int | None = Field(
        None, description="On-disk size of the uncompacted delta layer files."
    )
    embedding_sidecar_bytes: int | None = Field(
        None,
        description="On-disk size of embedding-derived files kept in the index (quantized codes/models, PCA, hub cache).",
    )
    raw_bytes: int | None = Field(
        None,
        description="Uncompressed baseline: what the live chunks' embeddings would weigh as full float32 (live_chunks * dimension * 4). Pair with index_size_bytes for the storage-savings ratio.",
    )
    index_size_bytes: int | None = Field(
        None,
        description="Persisted on-disk index size (base_bytes + delta_bytes). 0 in the not-loaded fallback where a disk walk isn't performed.",
    )
    compression_ratio: float | None = Field(
        None,
        description="raw_bytes / index_size_bytes (how many times smaller the index is than the raw float32 vectors). 0 before anything is persisted.",
    )
    base_deleted_chunks: int | None = Field(
        None,
        description="Rebuild advisory (live responses only): number of tombstoned chunks in the compacted base. Always 0 in the not-loaded fallback.",
    )
    base_deleted_fraction: float | None = Field(
        None,
        description="Rebuild advisory: fraction of the compacted base that is tombstoned (base_deleted_chunks / base size). Always 0 in the not-loaded fallback.",
    )
    rebuild_recommended: bool | None = Field(
        None,
        description="Rebuild advisory: true when base_deleted_fraction exceeds the ~5% threshold. Advisory only -- the server never auto-compacts on it. Always false in the not-loaded fallback.",
    )
    num_chunks: int | None = Field(
        None, description="Stored chunk count (from metadata)."
    )
    num_docs: int | None = Field(
        None, description="Stored document count (from metadata)."
    )


class ImportDocumentsRequest(BaseModel):
    documents: list[Document] = Field(..., min_length=1)


class Status6(Enum):
    processing = "processing"


class ImportDocumentsResponse(BaseModel):
    imported: int | None = None
    document_ids: list[int] | None = None
    index_id: str | None = None
    pending_total: int | None = None
    status: Status6 | None = None
    message: str | None = None


class PendingStatusResponse(BaseModel):
    index_id: str | None = None
    pending_count: int | None = None


class ProcessPendingResponse(BaseModel):
    index_id: str | None = None
    processed: int | None = None
    chunks_created: int | None = None
    chunk_ids: list[str] | None = Field(
        None, description="store.ChunkID values -- strings, as in AddDocumentsResponse."
    )


class Status7(Enum):
    cleared = "cleared"


class ClearPendingResponse(BaseModel):
    index_id: str | None = None
    status: Status7 | None = None
    message: str | None = None


class SyncDocumentInput(BaseModel):
    resource_id: str | None = Field(
        None, description="Deduplication key. Required when `shared` is true.\n"
    )
    text: str | None = Field(None, description="Document text content.")
    metadata: dict[str, str] | None = Field(
        None,
        description="Key-value metadata. Recognized keys include: `repo_id`,\n`file_path`, `commit_sha`, `title`, `author`, `url`,\n`resource_type`, `created_at` (RFC3339), `author_email`,\n`source_id`, `source_name`, `connector_id`, `content_id`,\n`content_type`, `thread_id`.\n",
    )


class SyncDocumentsRequest(BaseModel):
    user_id: str = Field(..., description="ID of the user performing the sync.")
    source_type: str = Field(
        ...,
        description="Integration source type (e.g. `github`, `confluence`, `slack`,\n`gmail`, `gdocs`).\n",
    )
    shared: bool | None = Field(
        False,
        description="When true, documents are added to a shared org-level index with\ndeduplication by `resource_id`. When false, documents go to the\nuser's personal index.\n",
    )
    documents: list[SyncDocumentInput] = Field(..., min_length=1)


class IndexType(Enum):
    personal = "personal"
    shared = "shared"


class SyncDocumentsResponse(BaseModel):
    synced: int | None = None
    org_id: str | None = None
    user_id: str | None = None
    source_type: str | None = None
    index_type: IndexType | None = None


class MultiSearchRequest(BaseModel):
    query: str = Field(..., description="Text query for semantic search.")
    k: int | None = Field(
        0,
        description="Maximum results. 0 (default) returns all relevant results with\nno limit.\n",
    )
    max_results: int | None = Field(
        None, deprecated=True, description="Deprecated: use `k` instead."
    )
    sources: list[str] | None = Field(
        None,
        description='Filter by source types (e.g. `["github", "slack"]`). Empty\nsearches all discovered sources.\n',
    )
    ef_search: int | None = Field(
        500, description="Search expansion factor for HNSW traversal."
    )
    include_text: bool | None = Field(
        False, description="Include chunk text content in results."
    )
    start_time: int | None = Field(
        None,
        description="Unix timestamp -- only return results created after this time.",
    )
    end_time: int | None = Field(
        None,
        description="Unix timestamp -- only return results created before this time.",
    )
    distance_threshold: float | None = Field(
        0.5,
        description="Maximum cosine distance for results. Lower values mean stricter\nmatching (0 = perfect match, 1 = orthogonal). Values less than or\nequal to zero are treated as the default (0.5).\n",
    )


class MultiSearchResult(BaseModel):
    chunk_id: int | None = None
    text: str | None = Field(
        None, description="Chunk text (only when `include_text` is true)."
    )
    distance: float | None = Field(
        None, description="Cosine distance from query (lower is better)."
    )
    source_type: str | None = None
    repo_id: str | None = None
    metadata: dict[str, Any] | None = Field(
        None,
        description="Metadata fields such as `file_path`, `commit_sha`, `title`,\n`url`, `author_name`, `author_email`, `source_id`,\n`source_name`, `connector_id`, `content_id`, `content_type`,\n`thread_id`, `resource_id`, `owner_user_id`.\n",
    )
    created_at: int | None = Field(
        None, description="Unix timestamp when the content was created."
    )
    shared: bool | None = Field(
        None, description="Whether this result is from a shared index."
    )


class MultiSearchResponse(BaseModel):
    results: list[MultiSearchResult] | None = None
    total: int | None = None
    query: str | None = None
    org_id: str | None = None
    user_id: str | None = None


class OrgIndexListResponse(BaseModel):
    indexes: list[IndexInfo] | None = None
    total: int | None = None
    org_id: str | None = None
    user_id: str | None = None


class SharedIndexListResponse(BaseModel):
    indexes: list[IndexInfo] | None = None
    total: int | None = None
    org_id: str | None = None


class Deleted(Enum):
    boolean_True = True


class DeleteTenantResponse(BaseModel):
    deleted: Deleted | None = None
    tenant_id: str | None = None
    name: str | None = None


class EmbeddingBackend1(Enum):
    ollama = "ollama"
    openai = "openai"
    local_onnx = "local_onnx"


class SwitchEmbeddingModelRequest(BaseModel):
    embedding_backend: EmbeddingBackend1 = Field(
        ...,
        description="Destination embedding backend. The HTTP API intentionally\nrejects `mock` — it is CLI-only.\n",
    )
    model: str = Field(
        ...,
        description="Destination model identifier.",
        max_length=256,
        pattern="^[A-Za-z0-9._:/\\-]{1,256}$",
    )
    dimension: int = Field(
        ...,
        description="Expected output dimension for the destination model.",
        ge=1,
        le=8192,
    )
    endpoint_override: str | None = Field(
        None,
        description="Optional URL (ollama / openai) or filesystem path\n(local_onnx) to override the default endpoint. Endpoints\nwith shell metacharacters are rejected.\n",
    )
    api_key: str | None = Field(
        None,
        description="Optional API key for the destination backend. Carried in\nmemory only — never echoed back in the job JSON.\n",
    )


class Status8(Enum):
    queued = "queued"


class SwitchEmbeddingModelResponse(BaseModel):
    job_id: str | None = None
    status: Status8 | None = None


class JobProgress(BaseModel):
    chunks_done: int | None = None
    chunks_total: int | None = None


class Kind(Enum):
    reembed = "reembed"


class Status9(Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class Job(BaseModel):
    job_id: str | None = None
    kind: Kind | None = None
    tenant_id: str | None = None
    index_id: str | None = None
    status: Status9 | None = None
    progress: JobProgress | None = None
    created_at: AwareDatetime | None = None
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    error: str | None = None


class JobListResponse(BaseModel):
    jobs: list[Job] | None = None
    total: int | None = None
    next_cursor: str | None = Field(
        None, description="Cursor to pass back as `?cursor=` for the next page."
    )


class GCResponse(BaseModel):
    index_id: str
    deleted_count: int = Field(
        ..., description="Number of expired documents deleted by the sweep."
    )


class AdminGCResponse(BaseModel):
    deleted_count: int = Field(
        ..., description="Total expired documents deleted across all loaded indexes."
    )


class AdminCleanupResponse(BaseModel):
    removed: list[str] = Field(
        ...,
        description="Absolute paths removed (or, under dry_run, that would be removed).",
    )
    freed_bytes: int
    min_age: str = Field(
        ...,
        description="Minimum-age cutoff actually applied, as a Go duration string.",
        examples=["1h"],
    )
    dry_run: bool = Field(..., description="Echoes whether the sweep was a dry run.")


class State(Enum):
    alive = "alive"
    suspect = "suspect"
    dead = "dead"


class ClusterNodeView(BaseModel):
    id: str | None = None
    addr: str | None = None
    zone: str | None = None
    state: State | None = None
    last_seen: AwareDatetime | None = None


class ClusterShardView(BaseModel):
    id: str | None = None
    primary: str | None = None
    replicas: list[str] | None = None
    zone_placement: dict[str, str] | None = None


class ListClusterNodesResponse(BaseModel):
    nodes: list[ClusterNodeView] | None = None
    leader: str | None = None


class ListClusterShardsResponse(BaseModel):
    shards: list[ClusterShardView] | None = None
    rf: int | None = Field(None, description="Configured replication factor.")


class Status10(Enum):
    ok = "ok"
    degraded = "degraded"
    unhealthy = "unhealthy"


class ClusterHealthResponse(BaseModel):
    status: Status10 | None = None
    cluster_size: int | None = None
    alive_nodes: int | None = None
    raft_has_leader: bool | None = None
    under_replicated_shards: int | None = None


class CreateAPIKeyRequest(BaseModel):
    user_id: str = Field(
        ..., description="Owning user ID. Must already exist inside the tenant."
    )
    name: str = Field(..., description="Human-readable label stored alongside the key.")


class CreateAPIKeyResponse(BaseModel):
    id: str = Field(..., description="Stable key identifier (e.g. `k_abc123`).")
    name: str
    user_id: str
    plaintext: str = Field(
        ...,
        description="The plaintext API token. RETURNED EXACTLY ONCE. The server\nstores only the argon2id hash; losing this value requires\nrotating the key.\n",
    )
    created_at: AwareDatetime


class APIKeyListItem(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: AwareDatetime
    last_used_at: AwareDatetime | None = Field(
        None, description="Set when the key has been validated at least once."
    )


class ListAPIKeysResponse(BaseModel):
    api_keys: list[APIKeyListItem]


class Provider(Enum):
    openai = "openai"
    ollama = "ollama"
    anthropic = "anthropic"


class LLMSettings(BaseModel):
    provider: Provider | None = None
    model: str | None = None
    api_key: str | None = Field(
        None,
        description="On read this field is masked (`***` + last four characters).\nOn write a masked sentinel preserves the existing key.\n",
    )
    base_url: str | None = Field(
        None, description="Optional base URL override. SSRF-validated server-side."
    )
    temperature: float | None = None
    max_tokens: int | None = None


class LLMSettingsPatch(BaseModel):
    provider: Provider | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class LicenseEntitlements(BaseModel):
    max_tenants: int | None = None
    max_memory_bytes: int | None = None
    max_cpu: int | None = None
    max_disk_bytes: int | None = None


class State1(Enum):
    unlicensed = "unlicensed"
    active = "active"
    grace = "grace"
    expired = "expired"
    mismatch = "mismatch"


class LicenseStatus(BaseModel):
    state: State1 | None = None
    license_id: str | None = None
    not_after: int | None = Field(
        None, description="Unix timestamp the license expires, if bound."
    )
    entitlements: LicenseEntitlements | None = None
    current_fingerprint: str | None = None
    bound_fingerprint: str | None = Field(
        None, description="Fingerprint the license is bound to, if activated."
    )
    fingerprint_match: bool | None = None
    grace_deadline: int | None = Field(
        None, description="Unix timestamp the grace period ends, if in the grace state."
    )
    last_error: str | None = None


class LicenseAuditEvent(BaseModel):
    time: AwareDatetime | None = None
    state: str | None = None
    detail: str | None = None


class ListDocumentEntry(BaseModel):
    id: str | None = Field(None, description="The document's external ID.")
    text: str | None = None
    metadata: dict[str, Any] | None = None


class ListDocumentsResponse(BaseModel):
    documents: list[ListDocumentEntry] | None = None
    next_cursor: str | None = Field(
        None,
        description="Cursor to pass back as `?cursor=` for the next page. Absent on the last page.",
    )


class BatchSearchRequest(BaseModel):
    queries: list[SearchRequest] = Field(
        ...,
        description="Up to 128 independent queries, each valid on its own against `/search`.",
        max_length=128,
    )


class BatchSearchResult(BaseModel):
    results: list[SearchResult] | None = None
    total: int | None = None
    error: str | None = Field(
        None,
        description="Set instead of `results`/`total` when this one query failed; the rest of the batch is unaffected.",
    )


class BatchSearchResponse(BaseModel):
    responses: list[BatchSearchResult] | None = Field(
        None, description="One entry per request query, in the same order."
    )


class Flushed(Enum):
    boolean_True = True


class FlushIndexResponse(BaseModel):
    flushed: Flushed | None = None


class Rebuilt(Enum):
    boolean_True = True


class RebuildGraphResponse(BaseModel):
    rebuilt: Rebuilt | None = None
    chunks: int | None = Field(
        None, description="Number of chunks the delta graph was rebuilt from."
    )
    wall_ms: int | None = Field(
        None, description="Wall-clock rebuild time in milliseconds."
    )


class CompactAllSkipped(BaseModel):
    index_id: str | None = None
    reason: str | None = None


class CompactAllResponse(BaseModel):
    tenant_id: str | None = None
    total_indexes: int | None = None
    queued: list[str] | None = Field(
        None, description="IDs of indexes newly scheduled by this request."
    )
    queued_count: int | None = None
    skipped: list[CompactAllSkipped] | None = Field(
        None,
        description="Indexes already queued or in flight, skipped rather than re-queued.",
    )
    skipped_count: int | None = None
    message: str | None = None


class State2(Enum):
    unknown = "unknown"
    verified = "verified"
    mismatch = "mismatch"
    external_unverified = "external_unverified"
    external_agree = "external_agree"
    external_diverged = "external_diverged"


class EmbedSpaceIndexRow(BaseModel):
    index_id: str | None = None
    tenant_id: str | None = None
    loaded: bool | None = Field(
        None,
        description="Whether this index is currently resident in memory (vs. classified by peeking its on-disk header).",
    )
    state: State2 | None = None
    embed_fingerprint: str | None = Field(
        None, description="The index's own stored embedding fingerprint."
    )
    detail: str | None = None
    checked_at: AwareDatetime | None = Field(
        None,
        description="When this row's state was last resolved. Absent if never checked.",
    )


class Policy(Enum):
    warn = "warn"
    refuse_search = "refuse_search"
    refuse_open = "refuse_open"


class EmbedSpaceAdminResponse(BaseModel):
    server_model: str | None = Field(
        None, description="Model name of the process-wide serving embedder."
    )
    server_dimension: int | None = None
    server_embed_fingerprint: str | None = None
    policy: Policy | None = Field(
        None,
        description="Fleet-level mismatch policy resolved from\nGRAPHANN_EMBEDDER_MISMATCH_POLICY. Global only -- per-index\nallow-list overrides are visible on each index's own status\nendpoint, not here.\n",
    )
    counts: dict[str, int] | None = Field(
        None,
        description='Count of indexes per state. Always has all six\nEmbedSpaceState keys present, even at zero, so callers can\ndistinguish "no indexes in this state" from "this state\ndoesn\'t exist". sum(counts.values()) == len(indexes).\n',
    )
    indexes: list[EmbedSpaceIndexRow] | None = None


class BackupChunkInfo(BaseModel):
    key: str | None = Field(None, description="Storage key for this chunk.")
    size: int | None = Field(None, description="Compressed on-storage size in bytes.")
    sha256: str | None = None
    uncompressed_size: int | None = None


class BackupMeta(BaseModel):
    tenant_id: str | None = None
    index_id: str | None = None
    graphann_version: str | None = None
    description: str | None = None
    labels: dict[str, str] | None = None


class BackupManifest(BaseModel):
    version: int | None = None
    id: str | None = Field(
        None, description="Same value as the backup id returned alongside the manifest."
    )
    created_at: AwareDatetime | None = None
    meta: BackupMeta | None = None
    chunks: list[BackupChunkInfo] | None = None
    total_size: int | None = None


class CreateBackupResponse(BaseModel):
    backup_id: str | None = None
    manifest: BackupManifest | None = None


class BackupSummary(BaseModel):
    ID: str | None = None
    TenantID: str | None = None
    IndexID: str | None = None
    CreatedAt: AwareDatetime | None = None
    TotalSize: int | None = None
    NumChunks: int | None = None


class ListBackupsResponse(BaseModel):
    backups: list[BackupSummary] | None = None


class RestoreBackupRequest(BaseModel):
    dest_index: str = Field(
        ...,
        description="Destination index within the path tenant. The destination directory must be empty -- restore refuses to overwrite existing data.",
    )


class Status11(Enum):
    restored = "restored"


class RestoreBackupResponse(BaseModel):
    status: Status11 | None = None
    index_id: str | None = None


class Status12(Enum):
    deleted = "deleted"


class DeleteBackupResponse(BaseModel):
    status: Status12 | None = None


class ErrorEnvelope(BaseModel):
    error: APIError
