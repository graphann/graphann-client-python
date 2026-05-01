# graphann

Official Python client SDK for the [GraphANN](https://graphann.com)
vector database.

`graphann` is a thin, strongly typed wrapper around the GraphANN HTTP
API. It supports both synchronous (`Client`) and asynchronous
(`AsyncClient`) workflows with full surface parity, hardened HTTP
defaults, and the cross-cutting concerns you would otherwise hand-roll
yourself: retries, request coalescing, response caching, gzip,
metrics hooks, and Pydantic v2 models for every payload.

- Python 3.10+
- httpx 0.27+ (sync + async)
- Pydantic 2.5+ for request/response validation
- Zero other runtime dependencies

## Installation

```bash
pip install graphann
```

## Quickstart

```python
from graphann import Client

with Client(
    base_url="https://api.graphann.com",
    api_key="sk_live_...",
    tenant_id="t_abc",
    timeout=30.0,
    max_retries=3,
) as client:
    # Health check
    health = client.health()
    assert health.status == "healthy"

    # Create an index and ingest a couple of documents
    index = client.create_index("t_abc", name="docs", description="Demo index")
    client.add_documents(
        "t_abc",
        index.id,
        [
            {"id": "doc-1", "text": "GraphANN is a storage-efficient vector database."},
            {"id": "doc-2", "text": "It supports incremental indexing and hot model swaps."},
        ],
    )

    # Search
    for hit in client.search("t_abc", index.id, query="vector database", k=5):
        print(hit.id, hit.score)

    # Optional cross-encoder reranking (no-op against servers without
    # --reranker-url configured)
    for hit in client.search(
        "t_abc",
        index.id,
        query="what does the standard say about audit trails?",
        k=10,
        rerank=True,        # opt-in per query
        candidate_k=50,     # HNSW pool fed to reranker (default max(4*k, 50))
    ):
        # hit.score is always the cosine similarity. hit.rerank_score
        # is non-None only when the server actually reranked this hit
        # — and when set, it drives the ordering.
        print(hit.id, hit.score, hit.rerank_score)
```

## Asynchronous usage

```python
import asyncio
from graphann import AsyncClient

async def main() -> None:
    async with AsyncClient(api_key="sk_live_...", tenant_id="t_abc") as client:
        results = await client.search("t_abc", "i_xyz", query="hello")
        for r in results:
            print(r.id, r.score)

        # Cursor pagination is also async-native:
        async for page in client.list_documents("t_abc", "i_xyz", page_size=100):
            for entry in page.items:
                print(entry.id)

asyncio.run(main())
```

## Errors

Every error raised by the SDK derives from `graphann.errors.GraphANNError`.
HTTP failures map to typed subclasses so you can write narrow `except`
clauses:

```python
from graphann.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

try:
    client.search("t_abc", "i_missing", query="hello")
except NotFoundError:
    print("index missing")
except RateLimitError as exc:
    print(f"slow down, retry after {exc.retry_after}s")
except AuthenticationError:
    print("invalid credentials")
```

## Cross-cutting features

- **Retries.** Exponential backoff with full jitter on `429`, `5xx`,
  and transport errors. The server's `Retry-After` header is honoured.
- **Singleflight.** Identical concurrent search calls collapse to a
  single upstream request so a thundering herd never reaches the
  database.
- **Response cache.** Opt-in LRU + TTL cache, automatically invalidated
  on writes from the same client.
- **gzip.** Request bodies larger than 64 KiB are compressed before
  transit.
- **Metrics hook.** Pass `metrics_hook=callable(name, value, labels)` to
  feed Prometheus or OpenTelemetry from any HTTP boundary.

## Type safety

The package ships with `py.typed` and is `mypy --strict` clean. All
request and response payloads round-trip through Pydantic v2 models.

## License

Commercial — see [LICENSE](./LICENSE).
