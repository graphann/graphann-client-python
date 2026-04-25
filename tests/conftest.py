"""Shared pytest fixtures.

The integration test guard lives here too: any test that requires a live
GraphANN server checks ``GRAPHANN_BASE_URL`` and skips otherwise.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from graphann import Client


@pytest.fixture
def base_url() -> str:
    """Default base URL for unit tests; never hit the network."""
    return "http://test.invalid"


@pytest.fixture
def client(base_url: str) -> Generator[Client, None, None]:
    """Bare client. Tests that need ``pytest_httpx`` or ``respx`` should
    construct their own client so they can attach mock transports.
    """
    c = Client(base_url=base_url, api_key="test", tenant_id="t_test", max_retries=0)
    yield c
    c.close()


@pytest.fixture
def integration_url() -> str | None:
    """Return the GRAPHANN_BASE_URL env var or ``None``.

    Integration tests use this to decide whether to run.
    """
    return os.environ.get("GRAPHANN_BASE_URL")


@pytest.fixture
def integration_api_key() -> str | None:
    return os.environ.get("GRAPHANN_API_KEY")
