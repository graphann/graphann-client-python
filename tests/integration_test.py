"""End-to-end integration test against a real GraphANN server.

Skipped unless ``GRAPHANN_BASE_URL`` (and optionally ``GRAPHANN_API_KEY``,
``GRAPHANN_TENANT_ID``) are set in the environment. The test exercises
the full ingest → search → cleanup loop so it can be run as a smoke
check after a server release.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from graphann import Client

pytestmark = pytest.mark.skipif(
    not os.environ.get("GRAPHANN_BASE_URL"),
    reason="set GRAPHANN_BASE_URL to run integration tests",
)


def _client() -> Client:
    return Client(
        base_url=os.environ["GRAPHANN_BASE_URL"],
        api_key=os.environ.get("GRAPHANN_API_KEY"),
        tenant_id=os.environ.get("GRAPHANN_TENANT_ID"),
        max_retries=3,
        timeout=60.0,
    )


def test_health_round_trip() -> None:
    with _client() as c:
        h = c.health()
    assert h.status == "healthy"


def test_full_ingest_and_search_round_trip() -> None:
    """Create a tenant, ingest, search, then tear everything down."""
    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"sdk-int-{suffix}"
    with _client() as c:
        t = c.create_tenant(name=tenant_id, id=tenant_id)
        try:
            idx = c.create_index(t.id, name=f"idx-{suffix}")
            c.add_documents(
                t.id,
                idx.id,
                [
                    {"id": "a", "text": "vector databases enable semantic search"},
                    {"id": "b", "text": "graphann uses LEANN-style storage savings"},
                ],
            )
            # Allow a moment for any async indexing on smaller boxes.
            time.sleep(0.2)
            results = c.search(t.id, idx.id, query="semantic search", k=3)
            assert results, "expected at least one search result"
            assert all(r.score >= 0.0 for r in results)
        finally:
            try:
                c.delete_tenant(t.id)
            except Exception:
                pass
