"""Tests for retry policy + sync client retry behaviour."""

from __future__ import annotations

import json
import random
from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock

from graphann import Client
from graphann._retry import RetryPolicy, compute_delay
from graphann.errors import RateLimitError


@pytest.fixture
def url() -> str:
    return "http://retry.invalid"


@pytest.fixture
def fast_sleep() -> Generator[list[float], None, None]:
    """Patch time.sleep so retry delays are recorded but don't block tests."""
    calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    with patch("graphann.client.time.sleep", side_effect=fake_sleep):
        yield calls


def test_compute_delay_uses_full_jitter() -> None:
    rng = random.Random(42)
    policy = RetryPolicy(max_retries=3, backoff_base=1.0, max_delay=10.0)
    delays = [compute_delay(i, policy, rng=rng) for i in range(4)]
    # Each delay must be in [0, min(max_delay, base * 2**attempt))
    caps = [1.0, 2.0, 4.0, 8.0]
    for cap, d in zip(caps, delays, strict=True):
        assert 0.0 <= d <= cap


def test_compute_delay_honours_retry_after() -> None:
    policy = RetryPolicy(max_retries=3, backoff_base=1.0, max_delay=30.0)
    d = compute_delay(0, policy, retry_after=5.0)
    assert d == 5.0
    # Clipped to max_delay
    assert compute_delay(0, policy, retry_after=999.0) == 30.0


def test_retry_after_disabled() -> None:
    policy = RetryPolicy(max_retries=3, backoff_base=1.0, max_delay=10.0, respect_retry_after=False)
    rng = random.Random(0)
    d = compute_delay(0, policy, retry_after=999.0, rng=rng)
    assert 0.0 <= d <= 1.0


def test_client_retries_on_429_and_succeeds(
    httpx_mock: HTTPXMock, url: str, fast_sleep: list[float]
) -> None:
    # First call: 429, second call: 200.
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        status_code=429,
        json={"error": {"code": "rate_limited", "message": "slow"}},
        headers={"Retry-After": "1"},
    )
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        json={"tenants": [{"id": "t_1", "name": "n"}], "total": 1},
    )

    with Client(base_url=url, api_key="k", tenant_id="t", max_retries=3) as c:
        tenants = c.list_tenants()

    assert [t.id for t in tenants] == ["t_1"]
    # We slept once at the Retry-After value.
    assert fast_sleep == [1.0]


def test_client_gives_up_after_max_retries(
    httpx_mock: HTTPXMock, url: str, fast_sleep: list[float]
) -> None:
    for _ in range(4):  # initial + 3 retries = 4
        httpx_mock.add_response(
            url=f"{url}/v1/tenants",
            method="GET",
            status_code=429,
            json={"error": {"code": "rate_limited", "message": "slow"}},
            headers={"Retry-After": "1"},
        )

    with (
        Client(base_url=url, api_key="k", tenant_id="t", max_retries=3) as c,
        pytest.raises(RateLimitError),
    ):
        c.list_tenants()

    # Three sleeps between four attempts.
    assert len(fast_sleep) == 3


def test_client_retries_on_503(httpx_mock: HTTPXMock, url: str, fast_sleep: list[float]) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        status_code=503,
        json={"error": {"code": "service_unavailable", "message": "overloaded"}},
        headers={"Retry-After": "2"},
    )
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        json={"tenants": [], "total": 0},
    )
    with Client(base_url=url, api_key="k", tenant_id="t", max_retries=2) as c:
        result = c.list_tenants()
    assert result == []
    assert fast_sleep == [2.0]


def test_max_retries_zero_disables_retries(
    httpx_mock: HTTPXMock, url: str, fast_sleep: list[float]
) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="GET",
        status_code=429,
        json={"error": {"code": "rate_limited", "message": "no"}},
    )
    with (
        Client(base_url=url, api_key="k", tenant_id="t", max_retries=0) as c,
        pytest.raises(RateLimitError),
    ):
        c.list_tenants()
    assert fast_sleep == []


def test_no_retry_on_400(httpx_mock: HTTPXMock, url: str, fast_sleep: list[float]) -> None:
    httpx_mock.add_response(
        url=f"{url}/v1/tenants",
        method="POST",
        status_code=400,
        json={"error": {"code": "bad_request", "message": "name required"}},
    )
    from graphann.errors import GraphANNError

    with (
        Client(base_url=url, api_key="k", tenant_id="t", max_retries=3) as c,
        pytest.raises(GraphANNError) as exc_info,
    ):
        c.create_tenant("x")
    assert exc_info.value.status_code == 400
    assert fast_sleep == []  # 4xx (other than 429) is not retriable
    # And we only sent one request total.
    assert len(httpx_mock.get_requests()) == 1
    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body == {"name": "x"}
