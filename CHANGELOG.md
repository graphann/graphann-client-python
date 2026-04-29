# Changelog

All notable changes to the `graphann` Python SDK are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
