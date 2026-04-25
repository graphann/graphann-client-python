"""Shared HTTP plumbing for the sync and async clients.

What lives here:

- The default httpx ``Timeout`` and ``Limits``.
- The user-agent string and ``MetricsHook`` protocol.
- :func:`build_request` — pure function that produces a fully formed
  ``httpx.Request`` ready for transport (handles JSON encoding, optional
  gzip, headers, query params).
- :class:`RequestPlan` — the sync/async clients construct this once per
  call and reuse it across retries so each retry replays the *same*
  bytes (otherwise the body gets re-encoded — wasteful — or, worse, the
  random JSON ordering of dict iteration produces a different hash for
  the cache key).
- :func:`process_response` — common response handling: 204 → ``None``,
  204-equivalent empty bodies → ``None``, error responses → typed
  exceptions, success → parsed JSON.
"""

from __future__ import annotations

import gzip
import json
import platform
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from ._version import __version__
from .errors import GraphANNError, NetworkError, error_for_response

__all__ = [
    "DEFAULT_GZIP_THRESHOLD",
    "DEFAULT_LIMITS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_USER_AGENT",
    "MetricsHook",
    "RequestPlan",
    "build_request",
    "build_user_agent",
    "is_retriable_transport_error",
    "parse_retry_after",
    "process_response",
    "safe_metrics",
    "wrap_transport_error",
]


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header value into seconds.

    Accepts both integer seconds and HTTP-date forms (RFC 7231).
    Returns ``None`` for missing or unparseable values.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        target = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    import datetime as _dt

    now = _dt.datetime.now(tz=target.tzinfo) if target.tzinfo else _dt.datetime.utcnow()
    return max(0.0, (target - now).total_seconds())


DEFAULT_TIMEOUT: httpx.Timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
DEFAULT_LIMITS: httpx.Limits = httpx.Limits(
    max_connections=20, max_keepalive_connections=10, keepalive_expiry=30.0
)
DEFAULT_GZIP_THRESHOLD: int = 64 * 1024  # 64 KiB


def build_user_agent(version: str = __version__) -> str:
    """Return the ``User-Agent`` string used by both clients."""
    py = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    plat = platform.platform(terse=True)
    return f"graphann-python/{version} ({py}; {plat})"


DEFAULT_USER_AGENT: str = build_user_agent()


@runtime_checkable
class MetricsHook(Protocol):
    """Callable observed at request boundaries.

    Implementations receive a metric ``name`` (e.g.
    ``"graphann.http.request_duration_seconds"``), the numeric ``value``,
    and a ``labels`` mapping. The hook is called from the same
    coroutine/thread issuing the request, so it must not block on I/O.
    """

    def __call__(
        self, name: str, value: float, labels: Mapping[str, str]
    ) -> None: ...  # pragma: no cover


@dataclass(slots=True)
class RequestPlan:
    """Materialised request ready for one or more httpx transport calls.

    The body bytes are pre-encoded (and possibly gzipped) so retries
    replay an identical payload. Headers include the auth/tenant headers
    plus content negotiation; ``params`` is left as a dict so httpx can
    serialise it.
    """

    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, Any] = field(default_factory=dict)
    body: bytes | None = None

    def cache_payload(self) -> bytes | None:
        """Return the bytes used for cache-key derivation."""
        return self.body


def _encode_body(
    body: Any,
    *,
    gzip_threshold: int,
    headers: dict[str, str],
) -> bytes | None:
    """Serialise ``body`` to JSON, optionally gzip-compressing it."""
    if body is None:
        return None
    if isinstance(body, (bytes, bytearray)):
        encoded = bytes(body)
    else:
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers.setdefault("Content-Type", "application/json")
    if gzip_threshold > 0 and len(encoded) >= gzip_threshold:
        encoded = gzip.compress(encoded)
        headers["Content-Encoding"] = "gzip"
    return encoded


def build_request(
    method: str,
    base_url: str,
    path: str,
    *,
    api_key: str | None,
    tenant_id: str | None,
    user_agent: str,
    body: Any = None,
    params: Mapping[str, Any] | None = None,
    extra_headers: Mapping[str, str] | None = None,
    gzip_threshold: int = DEFAULT_GZIP_THRESHOLD,
) -> RequestPlan:
    """Assemble a :class:`RequestPlan` for the given call.

    The output is intentionally not an ``httpx.Request`` so the same plan
    can be replayed against either an ``httpx.Client`` or
    ``httpx.AsyncClient`` without re-encoding.
    """
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
    if api_key:
        # Send both X-API-Key and Authorization: Bearer for compatibility
        # with deployments that strip one or the other at the edge.
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    if extra_headers:
        for k, v in extra_headers.items():
            headers[k] = v

    encoded = _encode_body(body, gzip_threshold=gzip_threshold, headers=headers)

    # Strip empty params so ``?prefix=&cursor=`` does not turn into noise.
    cleaned_params: dict[str, Any] = {}
    if params:
        for k, v in params.items():
            if v is None:
                continue
            cleaned_params[k] = v

    url = base_url.rstrip("/") + path
    return RequestPlan(
        method=method.upper(),
        url=url,
        headers=headers,
        params=cleaned_params,
        body=encoded,
    )


def _is_no_content(response: httpx.Response) -> bool:
    if response.status_code == 204:
        return True
    return response.status_code == 200 and not response.content


def process_response(response: httpx.Response) -> Any:
    """Decode an httpx response and raise typed errors on failures.

    Returns ``None`` for 204 / empty 200 bodies; otherwise returns the
    parsed JSON body. Non-2xx responses become typed exceptions.
    """
    if 200 <= response.status_code < 300:
        if _is_no_content(response):
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise GraphANNError(
                f"server returned non-JSON 2xx body: {exc}",
                status_code=response.status_code,
                response=response,
            ) from exc
    raise error_for_response(response)


def wrap_transport_error(exc: Exception) -> NetworkError:
    """Convert an httpx transport exception into :class:`NetworkError`."""
    return NetworkError(str(exc) or type(exc).__name__)


# Internal helper exposed for tests: indicates whether a transport failure
# should be retried (we retry connect/read errors but not, e.g., invalid
# URL exceptions which are caller bugs).
def is_retriable_transport_error(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
            httpx.PoolTimeout,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.RemoteProtocolError,
        ),
    )


# Re-export for use by clients.
DEFAULT_RETRIABLE_STATUS: frozenset[int] = frozenset({429, 502, 503, 504})


def safe_metrics(
    hook: Callable[[str, float, Mapping[str, str]], None] | None,
    name: str,
    value: float,
    labels: Mapping[str, str],
) -> None:
    """Invoke ``hook`` swallowing any exceptions it raises.

    Metrics callbacks must never break the calling code path — a faulty
    Prometheus client should not knock out customer search queries.
    """
    if hook is None:
        return
    try:
        hook(name, value, labels)
    except Exception:
        pass
