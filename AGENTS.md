# AGENTS.md — graphann Python SDK

Usage guide for coding agents working against the `graphann` Python SDK.
Every snippet below uses real method names and signatures from the
current source (`src/graphann/`). Do not invent methods or fields.

The SDK is a typed wrapper over the GraphANN HTTP API. Both `Client`
(sync) and `AsyncClient` (async) expose the same method set; the async
variant returns awaitables and yields async iterators for pagination.

## Install

```bash
pip install graphann==0.9.0
```

Requires Python 3.10+, httpx 0.27+, Pydantic 2.5+.

## Client construction and auth

```python
from graphann import Client

client = Client(
    base_url="https://api.graphann.com",
    api_key="sk_live_...",   # sent as the X-API-Key header
    tenant_id="t_abc",       # default tenant; methods still take tenant_id explicitly
    timeout=30.0,
    max_retries=3,
)
```

`Client` and `AsyncClient` are context managers — use `with` / `async
with` so the underlying httpx client is closed:

```python
with Client(base_url="https://api.graphann.com", api_key="sk_live_...") as client:
    client.health()

import asyncio
from graphann import AsyncClient

async def main() -> None:
    async with AsyncClient(base_url="https://api.graphann.com", api_key="sk_live_...") as client:
        await client.health()

asyncio.run(main())
```

Every method takes `tenant_id` (and `index_id` where relevant) as
explicit positional arguments. The `tenant_id` passed to the constructor
is a default used for auth scoping, not an implicit argument.

## Create tenant -> create index

```python
tenant = client.create_tenant(name="demo", id="t_abc")   # id optional; deterministic when set

index = client.create_index(
    "t_abc",
    name="docs",
    description="Demo index",
    compression="pq",       # "none" | "scalar" | "binary" | "pq" | "recompute" | "" ; optional
    approximate=True,       # enable HNSW; None defers to server default
)
print(index.id)
```

`create_tenant` raises `ConflictError` if the id already exists — catch
it and call `client.get_tenant(tenant_id)` to make the call idempotent.

## Ingest text documents

`add_documents` accepts dicts or `DocumentInput` models:

```python
resp = client.add_documents(
    "t_abc",
    index.id,
    [
        {"id": "doc-1", "text": "GraphANN is a storage-efficient vector database."},
        {"id": "doc-2", "text": "It supports incremental indexing and hot model swaps.",
         "metadata": {"section": "intro"}, "upsert": True},
    ],
)
print(resp.added, resp.index_id, resp.chunk_ids)
# resp.external_ids is populated ONLY when the server minted IDs
# (sharded ingest of id-less documents). Persist those as durable IDs.
```

## Ingest precomputed vectors

Put a `vector` on each document to skip server-side embedding. This is
all-or-nothing per batch: mixing vector and non-vector documents in one
call returns HTTP 400 (`ValidationError`). On the precomputed path the
per-document `upsert` flag is ignored — precomputed inserts always upsert
by external id.

```python
resp = client.add_documents(
    "t_abc",
    index.id,
    [
        {"id": "v-1", "text": "anchor text", "vector": [0.01, 0.02, 0.03, ...]},
        {"id": "v-2", "text": "another",     "vector": [0.04, 0.05, 0.06, ...]},
    ],
)
```

Vector length must match the index dimension once it is fixed; a fresh
index adopts the dimension of its first ingest.

## Search (rerank + ef_search)

`search` returns `list[SearchResult]`. Pass either `query` (text) or
`vector` — not neither (raises `ValueError`).

```python
for hit in client.search("t_abc", index.id, query="vector database", k=5):
    print(hit.id, hit.score, hit.metadata)
```

`hit.score` is always the first-stage cosine similarity. With reranking,
`hit.rerank_score` is non-None only when the server actually reranked the
hit, and when set it drives ordering:

```python
for hit in client.search(
    "t_abc",
    index.id,
    query="what does the standard say about audit trails?",
    k=10,
    rerank=True,        # opt-in; no-op when server has no --reranker-url
    candidate_k=50,     # HNSW pool fed to the reranker (default max(4*k, 50))
    rerank_k=10,        # how many to return after rerank (default = k)
    ef_search=128,      # per-query HNSW beam width; server clamps, default 64
):
    print(hit.id, hit.score, hit.rerank_score)
```

Vector-only requests ignore `rerank` (the cross-encoder needs query
text). Use `search_full(...)` instead of `search(...)` to get the full
`SearchResponse` envelope, including the sharded-cluster fields
`partial` / `shards_total` / `shards_ok` / `degraded_shards` (all `None`
on non-sharded deployments).

Filtering via `SearchFilter` (or a plain dict):

```python
from graphann.models import SearchFilter

hits = client.search(
    "t_abc", index.id, query="audit",
    filter=SearchFilter(
        repo_ids=["repo-1"],
        exclude_external_ids=["doc-9"],
        equals={"section": "intro"},          # string equality, all pairs must match
    ),
)
```

## Bulk ingest with defer_save / bulk + flush

For large loads, defer the per-batch save (and optionally the per-doc
HNSW insert), then persist once with `flush_index`:

```python
# bulk=True implies defer_save and defers the HNSW graph build to flush.
for batch in batches:
    client.add_documents("t_abc", index.id, batch, bulk=True)

flushed = client.flush_index("t_abc", index.id)   # builds deferred graph + persists
print(flushed.flushed)
```

`defer_save=True` keeps data searchable in memory but unsaved (flush to
persist). `bulk=True` data is not searchable until the graph is built;
as a safety net the first search against a pending build triggers it
server-side ("build-on-read"). Both default to omitted, preserving the
per-batch, immediately-searchable behavior.

## API keys: create / list / revoke

```python
# create_api_key(tenant_id, *, name, user_id="")
key = client.create_api_key("t_abc", name="ci-key", user_id="u_1")
print(key.id, key.name, key.plaintext)   # plaintext is the one-time secret
```

The request body is `{"user_id": ..., "name": ...}`; both fields are
sent. `name` is required (the key's label); `user_id` is optional — an
empty `user_id` scopes the key to the tenant rather than a specific
user.

```python
listing = client.list_api_keys("t_abc")
for item in listing.api_keys:          # wrapper field is "api_keys"
    print(item.id, item.name, item.user_id, item.last_used_at)

client.revoke_api_key("t_abc", key.id)
```

`ApiKey` fields: `id`, `name`, `user_id`, `created_at`, `last_used_at`,
and `plaintext` (populated only by `create_api_key`).

## Error handling

Every SDK error derives from `graphann.errors.GraphANNError`. HTTP
failures map to typed subclasses:

```python
from graphann.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ValidationError,
)

try:
    client.search("t_abc", "i_missing", query="hello")
except NotFoundError:
    ...
except RateLimitError as exc:
    print(exc.retry_after)            # seconds; the SDK already retried per max_retries
except ValidationError:
    ...                               # 400, e.g. mixed vector/non-vector batch
```

`create_index` / `create_tenant` raise `ConflictError` on duplicate ids;
`compact_index` and `rebuild_graph` raise `ConflictError` when an
operation is already in progress.

## Key gotchas

- The `plaintext` secret from `create_api_key` is returned ONCE. Persist
  it immediately; the server cannot reveal it again. List responses never
  carry it.
- List response wrapper is `api_keys`, not `keys`. The one-time secret
  field is `plaintext`, not `key`.
- Precomputed-vector ingest is all-or-nothing per batch; mixing
  vector and non-vector documents returns HTTP 400.
- 16 MB request-body cap. Precomputed batches are limited to roughly
  1700 documents — chunk large loads.
- `delete_chunks` posts the full id list in the body to a placeholder
  path (`.../chunks/0`); the path id is not meaningful. Pass the chunk
  ids as the list argument.
- `bulk`-ingested data is not searchable until `flush_index` (or the
  first build-on-read search) runs.
- `search` requires either `query` or `vector`; passing neither raises
  `ValueError` before any HTTP call.
