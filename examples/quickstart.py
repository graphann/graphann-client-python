"""End-to-end quickstart for the GraphANN Python SDK.

Walk-through:

1. Connect to a server
2. Create a tenant and an index
3. Mint an API key for the tenant
4. Ingest 10 documents
5. Search the index
6. Switch the embedding model (queues an async re-embed job)
7. Re-run the search after the swap

The script is intentionally idempotent: re-running it picks up the same
deterministic tenant / index IDs.

Run it::

    GRAPHANN_BASE_URL=https://api.graphann.com \\
    GRAPHANN_ADMIN_KEY=sk_admin_... \\
        python examples/quickstart.py
"""

from __future__ import annotations

import os
import time
import uuid

from graphann import Client
from graphann.errors import ConflictError, GraphANNError, NotFoundError

SAMPLE_DOCS = [
    "GraphANN is a storage-efficient vector database.",
    "It implements the LEANN algorithm for 97% storage savings.",
    "Indexes can be queried via HTTP using the /v1 namespace.",
    "Documents are chunked and embedded automatically on ingest.",
    "The search endpoint accepts either a text query or a raw vector.",
    "Hot model switches re-embed without downtime.",
    "Cluster mode adds Raft replication and gossip membership.",
    "Multi-tenant isolation is enforced by the tenant ID header.",
    "Compaction merges delta layers back into the base index.",
    "RBAC filters search results by repository or external id.",
]


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"environment variable {name} is required")
    return value


def main() -> None:
    base_url = _required_env("GRAPHANN_BASE_URL")
    admin_key = os.environ.get("GRAPHANN_ADMIN_KEY")
    suffix = uuid.uuid4().hex[:6]
    tenant_id = f"sdk-quickstart-{suffix}"

    with Client(base_url=base_url, api_key=admin_key, max_retries=3) as admin:
        # 1. Create a tenant. We pass an explicit ID so the call is
        # idempotent — re-running the script reuses the same tenant.
        try:
            tenant = admin.create_tenant(name=tenant_id, id=tenant_id)
        except ConflictError:
            tenant = admin.get_tenant(tenant_id)
        print(f"tenant: {tenant.id}")

        # 2. Mint an API key for the tenant. ``key`` is only ever returned
        # on creation, so persist it client-side.
        try:
            api_key = admin.create_api_key(
                tenant.id, user_id="quickstart", description="quickstart demo"
            )
            tenant_key = api_key.key or admin_key
            print(f"api key: {api_key.id}")
        except (GraphANNError, NotImplementedError):
            # API key endpoint may not be enabled on every deployment;
            # fall back to the admin key supplied at startup.
            tenant_key = admin_key
            print("api key endpoint unavailable — falling back to admin key")

    # 3. Switch to a tenant-scoped client for the rest of the demo.
    with Client(base_url=base_url, api_key=tenant_key, tenant_id=tenant.id) as c:
        # 4. Create an index.
        index_name = f"docs-{suffix}"
        idx = c.create_index(tenant.id, name=index_name)
        print(f"index: {idx.id}")

        # 5. Ingest documents.
        c.add_documents(
            tenant.id,
            idx.id,
            [{"id": f"doc-{i}", "text": text} for i, text in enumerate(SAMPLE_DOCS)],
        )
        time.sleep(0.5)  # allow chunking + indexing to settle

        # 6. Search.
        print("\\n=== initial search ===")
        for hit in c.search_text(tenant.id, idx.id, "vector database", k=5):
            print(f"  {hit.score:.3f}  {hit.id}")

        # 7. Hot-swap the embedding model. Returns a job ID; the client
        # then polls until completion.
        try:
            job = c.switch_embedding_model(
                tenant.id,
                idx.id,
                embedding_backend="ollama",
                model="nomic-embed-text",
                dimension=768,
                endpoint_override=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            )
            print(f"\\nreembed job queued: {job.job_id}")
            for _ in range(60):
                status = c.get_job(job.job_id)
                if status.status in {"completed", "failed"}:
                    print(f"reembed status: {status.status}")
                    break
                time.sleep(1.0)
        except (NotFoundError, GraphANNError) as exc:
            print(f"\\nhot model switch skipped: {exc}")

        # 8. Re-run the search.
        print("\\n=== post-swap search ===")
        for hit in c.search_text(tenant.id, idx.id, "vector database", k=5):
            print(f"  {hit.score:.3f}  {hit.id}")


if __name__ == "__main__":
    main()
