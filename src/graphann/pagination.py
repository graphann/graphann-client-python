"""Cursor-based pagination iterators.

Both iterators are thin wrappers around a fetch callable that returns one
page at a time. The fetcher receives the previous page's cursor (or
``None`` for the initial fetch) and returns ``(items, next_cursor)``.
The iterator stops when ``next_cursor`` is empty or ``None``.

Usage (sync)::

    for page in client.list_documents(index_id="i_..."):
        for entry in page.items:
            ...

Usage (async)::

    async for page in async_client.list_documents(index_id="i_..."):
        ...
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

__all__ = ["AsyncPageIterator", "Page", "PageIterator"]


T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    """One page of paginated results.

    ``items`` holds the page contents; ``cursor`` is the cursor that
    fetched this page (``None`` for the first page). ``next_cursor`` is
    the value the iterator passes to the fetcher for the next call.
    """

    items: list[T]
    cursor: str | None
    next_cursor: str | None

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


_FetchSync = Callable[[str | None], tuple[list[T], str | None]]
_FetchAsync = Callable[[str | None], Awaitable[tuple[list[T], str | None]]]


class PageIterator(Generic[T]):
    """Iterator that fetches one page per ``__next__`` call."""

    def __init__(self, fetch: _FetchSync[T]) -> None:
        self._fetch = fetch
        self._cursor: str | None = None
        self._exhausted = False
        self._first = True

    def __iter__(self) -> PageIterator[T]:
        return self

    def __next__(self) -> Page[T]:
        if self._exhausted:
            raise StopIteration
        prev_cursor = self._cursor
        items, next_cursor = self._fetch(prev_cursor if not self._first else None)
        self._first = False
        if not next_cursor:
            self._exhausted = True
        self._cursor = next_cursor
        return Page(items=items, cursor=prev_cursor, next_cursor=next_cursor)


class AsyncPageIterator(Generic[T]):
    """Async counterpart of :class:`PageIterator`."""

    def __init__(self, fetch: _FetchAsync[T]) -> None:
        self._fetch = fetch
        self._cursor: str | None = None
        self._exhausted = False
        self._first = True

    def __aiter__(self) -> AsyncPageIterator[T]:
        return self

    async def __anext__(self) -> Page[T]:
        if self._exhausted:
            raise StopAsyncIteration
        prev_cursor = self._cursor
        items, next_cursor = await self._fetch(prev_cursor if not self._first else None)
        self._first = False
        if not next_cursor:
            self._exhausted = True
        self._cursor = next_cursor
        return Page(items=items, cursor=prev_cursor, next_cursor=next_cursor)
