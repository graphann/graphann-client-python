# Changelog

All notable changes to the `graphann` Python SDK are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
