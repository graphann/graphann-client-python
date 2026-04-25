"""LRU + TTL response cache used by the sync and async clients.

The cache is opt-in: clients construct it only when ``cache_ttl`` (or
``cache_max_entries``) is set on the public ``Client`` /
``AsyncClient``. Keys are derived from ``(method, path, body_hash,
tenant_id)`` so a request that mutates the tenant header naturally
produces a different cache key.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

__all__ = ["ResponseCache", "make_cache_key"]


def _hash_body(body: bytes | None) -> str:
    if body is None or not body:
        return "_"
    h = hashlib.blake2b(body, digest_size=16)
    return h.hexdigest()


def make_cache_key(
    method: str,
    path: str,
    body: bytes | None,
    tenant_id: str | None,
) -> str:
    """Return a stable string key for cache lookups.

    The key includes the tenant header so a swap from one tenant to
    another does not return another tenant's cached payload. ``body`` is
    hashed because storing the raw bytes inside the key would balloon
    memory for large search vectors.
    """
    return f"{method.upper()}|{path}|{tenant_id or ''}|{_hash_body(body)}"


@dataclass(slots=True)
class _Entry:
    """Single cache entry.

    ``expires_at`` is monotonic-clock seconds, not wall clock — TTLs are
    immune to system-clock changes.
    """

    value: Any
    expires_at: float


class ResponseCache:
    """Thread-safe LRU + TTL cache.

    The cache is bounded by entry count (``max_entries``); inserting past
    the cap evicts the least-recently-used entry. Expired entries are
    removed lazily on access. The same instance is shared between the
    sync and async clients (locking is handled internally).
    """

    def __init__(self, *, ttl: float, max_entries: int = 256) -> None:
        if ttl <= 0:
            raise ValueError("cache ttl must be > 0")
        if max_entries <= 0:
            raise ValueError("cache max_entries must be > 0")
        self._ttl = float(ttl)
        self._max = int(max_entries)
        self._data: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Return the cached value or ``None`` if missing/expired."""
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any) -> None:
        """Store a value under ``key`` with the configured TTL."""
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            self._data[key] = _Entry(value=value, expires_at=expires_at)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def invalidate(self, key: str) -> None:
        """Drop a single cache entry."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Drop all cache entries."""
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:  # pragma: no cover — diagnostic only
        with self._lock:
            return len(self._data)
