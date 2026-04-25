"""Retry policy with exponential backoff and full jitter.

Used by both the sync and async HTTP layers. The policy intentionally
treats ``Retry-After`` as authoritative — when the server tells us how
long to wait, we wait at least that long. Otherwise, we use exponential
backoff capped at :pyattr:`RetryPolicy.max_delay` with full jitter
(`min(cap, base * 2**attempt) * random()`), which is the AWS-recommended
schedule for a single client retrying against a contended endpoint.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

__all__ = ["RetryPolicy", "compute_delay"]


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry behaviour.

    Attributes:
        max_retries: Maximum number of retry attempts in addition to the
            initial request. ``0`` disables retrying entirely.
        backoff_base: Base delay (seconds) used in the exponential schedule.
        max_delay: Upper bound (seconds) on a single retry sleep.
        respect_retry_after: When ``True`` (default), the SDK honours the
            ``Retry-After`` header from 429 / 503 responses, sleeping for
            at least that long before the next attempt.
        retry_on_status: HTTP statuses that count as transient and trigger
            a retry. Defaults to ``{429, 502, 503, 504}``.
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    max_delay: float = 30.0
    respect_retry_after: bool = True
    retry_on_status: frozenset[int] = frozenset({429, 502, 503, 504})


def compute_delay(
    attempt: int,
    policy: RetryPolicy,
    *,
    retry_after: float | None = None,
    rng: random.Random | None = None,
) -> float:
    """Return the seconds to sleep before retry attempt ``attempt``.

    ``attempt`` is 0-indexed: ``0`` is the delay before the first retry.

    The schedule is full-jitter exponential backoff: ``delay = random() *
    min(max_delay, backoff_base * 2**attempt)``. When ``retry_after`` is
    provided AND the policy honours it, we sleep for at least that value
    (clipped to ``max_delay``). Honouring takes precedence over the
    schedule because the server has authoritative knowledge of when it
    will be ready again.
    """
    if retry_after is not None and policy.respect_retry_after:
        return min(policy.max_delay, max(0.0, retry_after))
    exp = float(policy.backoff_base) * float(2**attempt)
    cap: float = min(policy.max_delay, exp)
    sample: float = rng.random() if rng is not None else random.random()
    return float(sample * cap)
