# Changelog

All notable changes to the `graphann` Python SDK are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-06-10

### Added

- Precomputed-vector ingest: `DocumentInput.vector: list[float] | None`.
  When **every** document in a batch carries a vector the server skips
  embedding entirely; mixed batches (some with, some without) are
  rejected with HTTP 400. Vector length must match the index dimension
  once set; a fresh index adopts the dimension of the first ingest.
  Precomputed inserts upsert by external ID (the per-document `upsert`
  flag only applies on the text path). The 16 MB request-body cap limits
  precomputed batches to roughly 1700 documents.
- Bulk-load ingest options: `Client.add_documents` /
  `AsyncClient.add_documents` accept `defer_save: bool | None` (skip the
  per-batch save; data stays searchable, persist via `flush_index`) and
  `bulk: bool | None` (implies `defer_save` and defers the per-document
  HNSW insert — the delta graph is built once at flush; bulk data is not
  searchable until then, except that the first search against a pending
  build triggers it server-side, "build-on-read"). Defaults (`None`,
  omitted from the wire) preserve the per-batch, immediately-searchable
  behavior.
- `Client.flush_index` / `AsyncClient.flush_index` — `POST .../flush`.
  Persists the live index's in-memory delta and builds any pending
  bulk-deferred graph in the same flush. Returns the new `FlushResponse`
  model (`flushed: bool`). Safe to call on a clean index.
- `Client.rebuild_graph` / `AsyncClient.rebuild_graph` — `POST
  .../rebuild-graph`. In-place delta-HNSW rebuild for indexes ingested
  before the 2026-06 neighbor-selection fix. Returns the new
  `RebuildGraphResponse` model (`rebuilt`, `chunks`, `wall_ms`); raises
  `ConflictError` (409) while a compaction is in progress.
- Per-query `ef_search`: new field on `SearchRequest` and keyword
  argument on `search`. `0`/omitted uses the server default
  (`--search-ef`, 64). The server clamps rather than rejects (negative →
  default, cap 2000); binary/PQ flat-scan modes ignore it.
- `Client.search_full` / `AsyncClient.search_full` — identical signature
  to `search` but returns the full `SearchResponse` envelope instead of
  just `results`.
- Sharded-search metadata on `SearchResponse` (optional, `None` outside
  sharded cluster deployments): `partial: bool | None`,
  `shards_total: int | None`, `shards_ok: int | None`, and
  `degraded_shards: list[str] | None` (present only when non-empty).
  `partial=True` means at least one shard contributed nothing. Caveats
  per the server contract: rerank options are not applied on the sharded
  path, and results are deduped by external ID keeping the highest
  score.
- `AddDocumentsResponse.external_ids: list[str] | None` — populated only
  when the server minted external IDs (sharded ingest of id-less
  documents; the external ID is the shard routing key). One entry per
  submitted document, positionally aligned with the request array —
  persist these as the durable document IDs.

### Fixed

- Body-less mutating requests (`compact_index`, `clear_index`,
  `process_pending`, `run_index_gc`, `run_admin_gc`, `cleanup_orphans`,
  and the new `flush_index` / `rebuild_graph`) now send an empty JSON
  object `{}` with `Content-Type: application/json`. Current servers
  reject any POST without that header (HTTP 400), so these calls were
  broken against 2026-06 servers.

### Changed

- `update_index` docstring documents the compression semantics: the
  change persists metadata only (no rebuild) and takes effect at the
  next compaction; `""` and `"none"` both fold to the server's
  `--default-compression`.
- `compact_index` docstring clarifies the server replies `200 OK` with
  `{"index_id", "status": "compacting", "message"}` and that compaction
  completes asynchronously (no poll endpoint — observe via live-stats).

## [0.6.0] - 2026-05-01

### Added

- `SearchRequest.rerank`, `SearchRequest.candidate_k`, `SearchRequest.rerank_k`
  fields wire the optional cross-encoder reranker. `Client.search` /
  `AsyncClient.search` accept matching `rerank`, `candidate_k`, and
  `rerank_k` keyword arguments. When the server has a reranker
  configured (via `--reranker-url`), set `rerank=True` to rescore the
  top-`candidate_k` HNSW candidates and return the top-`rerank_k`
  (or top-`k`). Defaults: `candidate_k = max(4*k, 50)` (server clamps
  to `[k, 1000]`), `rerank_k = k`. No-op against non-rerank-aware
  servers — safe to roll out unconditionally.
- `SearchResult.rerank_score: float | None` — populated only when the
  server actually applied the reranker. Carries the cross-encoder's
  native relevance score (different scale from cosine, typically
  -10..10 for bge-reranker-v2-m3). When non-`None` it also reflects
  the result ordering; when `None`, ordering is by `score` (cosine).

### Unchanged

- `SearchResult.score` is still always the first-stage cosine
  similarity, regardless of rerank state. Existing client code that
  only reads `score` keeps working — even when accidentally hitting a
  rerank-enabled endpoint.

## [0.5.0] - 2026-04-30

### Changed

- `Client.cleanup_orphans` / `AsyncClient.cleanup_orphans` accept new
  optional keyword arguments: `min_age: str = ""` (Go duration string,
  e.g. `"1h"`, `"24h"`, `"30m"`; empty uses server default of 1h) and
  `dry_run: bool = False` (preview mode — server enumerates without
  removing). Pre-existing call sites that pass no arguments are
  unaffected.
- `CleanupOrphansResponse` gains `min_age: str` and `dry_run: bool`
  fields echoing what the server applied. Both default to empty/false
  when the server omits them (older servers).

## [0.3.0] - 2026-04-28

### Removed (BREAKING)

- `Client.search_text` / `AsyncClient.search_text` — deleted server-side
  (`POST .../search/text` no longer exists). Use `Client.search` with the
  `query` parameter instead.
- `Client.search_vector` / `AsyncClient.search_vector` — deleted
  server-side (`POST .../search/vector` no longer exists). Use
  `Client.search` with the `vector` parameter instead.
- `Client.build_index` / `AsyncClient.build_index` — was a stub no-op on
  the server; endpoint removed.

### Added

- `Client.upsert_resource` / `AsyncClient.upsert_resource` — `PUT
  /v1/tenants/{tenantID}/indexes/{indexID}/resources/{resourceID}`. Atomic
  create-or-replace: parses the text, chunks it, embeds it, and swaps out
  any prior chunks for that resource in one request. Returns
  `UpsertResourceResponse` with `resource_id`, `chunks_added`,
  `chunks_tombstoned`, and `operation` (`"create"` or `"update"`).
- `UpsertResourceRequest` and `UpsertResourceResponse` Pydantic models
  exported from `graphann.models`.

### Changed

- `CreateIndexRequest` and `UpdateIndexRequest` gain two optional fields:
  `compression` (`"none" | "scalar" | "binary" | "pq" | "recompute" | ""`)
  and `approximate` (`bool`).
- `Index` response model gains `compression` (`str | None`) and
  `approximate` (`bool | None`).
- `SearchFilter` gains `equals` (`dict[str, str] | None`) for generic
  metadata pre-filtering.
- `compact_index` now raises `ConflictError` (HTTP 409) when a compaction
  is already running — callers should catch and retry after a backoff.

## [0.2.0] - 2026-04-26

### Changed

No code changes in the Python SDK. Version bumped to maintain alignment
with sibling SDKs (Go, Rust, TypeScript) after a cross-SDK
naming-standardization pass. Python's existing names were already the
canonical form, so callers see no API change.

## [0.1.1] - 2026-04-25

### Added

- `Client.get_chunk` / `AsyncClient.get_chunk` — `GET
  /v1/tenants/{tenantID}/indexes/{indexID}/chunks/{chunkID}`. Returns the
  new `Chunk` model.
- `Client.delete_chunks` / `AsyncClient.delete_chunks` — `DELETE
  /v1/tenants/{tenantID}/indexes/{indexID}/chunks/{chunkID}`. Sends the
  full id list in the request body in a single call (matches the Go SDK
  `DeleteChunks` semantics; the path id is a placeholder).

### Changed

- LLM settings now hit the canonical `/v1/orgs/{orgID}/llm-settings`
  routes instead of the unwired `/v1/orgs/{orgID}/settings/llm` paths.
- `update_llm_settings` switched from `PUT` to `PATCH` (partial-merge)
  and now returns the raw `LLMSettings` payload — the previous envelope
  (`message` / `org_id` / `settings`) is no longer emitted by the
  server. Function signatures are unchanged.

## [0.1.0] - 2026-04-25

### Added

- Initial public release of the synchronous `Client` and asynchronous
  `AsyncClient`.
- Full surface coverage for the v1 HTTP API: tenants, indexes, documents,
  search (hybrid / text / vector), batch import, index maintenance
  (compact / clear / build), live stats, hot model switching, async jobs,
  cluster introspection, org-level multi-source sync, LLM settings,
  API-key administration.
- Hardened HTTP transport: tunable timeouts, connection pooling, automatic
  gzip on request bodies larger than 64 KiB, exponential backoff with
  full jitter, and `Retry-After` header handling on 429/503.
- Pydantic v2 request and response models with strict validation.
- Typed exception hierarchy (`GraphANNError`, `AuthenticationError`,
  `AuthorizationError`, `NotFoundError`, `ConflictError`,
  `PayloadTooLargeError`, `RateLimitError`, `ServerError`,
  `NetworkError`, `ValidationError`).
- Cursor pagination via `PageIterator` and `AsyncPageIterator` for
  `list_documents` and `list_jobs`.
- Singleflight coalescing of duplicate concurrent search calls (sync and
  async variants) plus an opt-in LRU + TTL response cache.
- Optional `metrics_hook` callable for Prometheus / OpenTelemetry
  integration.
- `examples/quickstart.py` demonstrating tenant / index / ingest / search
  / hot-model-switch round-trips.
