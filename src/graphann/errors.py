"""Exception hierarchy for the GraphANN SDK.

The mapping between server error codes / HTTP status and these exception
classes is centralised in :func:`error_for_response` so both the sync and
async clients raise consistent typed errors.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError as _PydanticValidationError

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "GraphANNError",
    "NetworkError",
    "NotFoundError",
    "PayloadTooLargeError",
    "RateLimitError",
    "ServerError",
    "ValidationError",
    "error_for_response",
]


class GraphANNError(Exception):
    """Base class for every error raised by the SDK.

    Carries the HTTP status code, the parsed server error code (when
    available), the human-readable message, and the optional ``details``
    payload returned by the server.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any = None,
        request: httpx.Request | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        self.request = request
        self.response = response

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"message={self.message!r}, "
            f"status_code={self.status_code!r}, "
            f"code={self.code!r})"
        )


class AuthenticationError(GraphANNError):
    """Raised on HTTP 401 responses."""


class AuthorizationError(GraphANNError):
    """Raised on HTTP 403 responses."""


class NotFoundError(GraphANNError):
    """Raised on HTTP 404 responses."""


class ConflictError(GraphANNError):
    """Raised on HTTP 409 responses."""


class PayloadTooLargeError(GraphANNError):
    """Raised on HTTP 413 responses."""


class RateLimitError(GraphANNError):
    """Raised on HTTP 429 responses.

    The ``retry_after`` attribute carries the parsed ``Retry-After``
    header value in seconds. The header may be missing — in that case
    ``retry_after`` is ``None`` and callers should fall back to their
    default backoff schedule.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(GraphANNError):
    """Raised on HTTP 5xx responses."""


class NetworkError(GraphANNError):
    """Raised when the underlying httpx transport fails before a response."""


class ValidationError(GraphANNError):
    """Raised when a Pydantic model fails to validate.

    Wraps the original :class:`pydantic.ValidationError` in
    :attr:`pydantic_error` so callers that need the full structured detail
    can still inspect it.
    """

    def __init__(
        self,
        message: str,
        *,
        pydantic_error: _PydanticValidationError | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.pydantic_error = pydantic_error


def _extract_error_payload(response: httpx.Response) -> tuple[str | None, str, Any]:
    """Pull ``code``/``message``/``details`` from a server error envelope.

    The server uses ``{"error": {"code": ..., "message": ..., "details": ...}}``.
    If the body is not JSON or does not match that shape, fall back to the
    HTTP reason phrase.
    """
    try:
        payload = response.json()
    except Exception:  # pragma: no cover — body parsing is best-effort
        return None, response.text or response.reason_phrase or "request failed", None

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            msg = err.get("message") or response.reason_phrase or "request failed"
            details = err.get("details")
            return (
                str(code) if code is not None else None,
                str(msg),
                details,
            )
        # Some endpoints (notably ones written to status pages) embed the
        # message at the top level. Be permissive.
        msg = payload.get("message") or payload.get("error")
        if isinstance(msg, str) and msg:
            return None, msg, None

    return None, response.reason_phrase or "request failed", None


def error_for_response(response: httpx.Response) -> GraphANNError:
    """Map an HTTP error response to the appropriate SDK exception.

    Caller is responsible for ensuring ``response.status_code`` indicates
    an error (>= 400). The function reads the response body so it must
    only be called on already-buffered responses.
    """
    status = response.status_code
    code, message, details = _extract_error_payload(response)
    request = response.request
    common = {
        "status_code": status,
        "code": code,
        "details": details,
        "request": request,
        "response": response,
    }

    if status == 401:
        return AuthenticationError(message, **common)
    if status == 403:
        return AuthorizationError(message, **common)
    if status == 404:
        return NotFoundError(message, **common)
    if status == 409:
        return ConflictError(message, **common)
    if status == 413:
        return PayloadTooLargeError(message, **common)
    if status == 429:
        from ._http import parse_retry_after

        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        return RateLimitError(message, retry_after=retry_after, **common)
    if 500 <= status < 600:
        if status == 503:
            # 503 may carry Retry-After (overload guard) — surface it on
            # the ServerError attribute so callers can honour it.
            from ._http import parse_retry_after

            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            err = ServerError(message, **common)
            err.retry_after = retry_after  # type: ignore[attr-defined]
            return err
        return ServerError(message, **common)
    return GraphANNError(message, **common)
