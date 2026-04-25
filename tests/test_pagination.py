"""Tests for the pagination iterators."""

from __future__ import annotations

import pytest

from graphann.pagination import AsyncPageIterator, Page, PageIterator


def test_sync_pagination_terminates_when_cursor_empty() -> None:
    pages = [
        ([1, 2], "c1"),
        ([3, 4], None),
    ]
    calls: list[str | None] = []

    def fetch(cursor: str | None) -> tuple[list[int], str | None]:
        calls.append(cursor)
        return pages.pop(0)

    it = PageIterator(fetch)
    p1 = next(it)
    assert p1.items == [1, 2]
    assert p1.next_cursor == "c1"
    p2 = next(it)
    assert p2.items == [3, 4]
    assert p2.next_cursor is None
    with pytest.raises(StopIteration):
        next(it)
    assert calls == [None, "c1"]


def test_sync_iter_consumes_all() -> None:
    pages = [
        ([1], "a"),
        ([2], "b"),
        ([3], None),
    ]

    def fetch(cursor: str | None) -> tuple[list[int], str | None]:
        return pages.pop(0)

    collected: list[int] = []
    for page in PageIterator(fetch):
        collected.extend(page.items)
    assert collected == [1, 2, 3]


def test_page_dataclass_iterates() -> None:
    p = Page(items=[1, 2, 3], cursor=None, next_cursor=None)
    assert list(p) == [1, 2, 3]
    assert len(p) == 3


@pytest.mark.asyncio
async def test_async_pagination() -> None:
    pages = [
        ([10], "next-1"),
        ([20], None),
    ]

    async def fetch(cursor: str | None) -> tuple[list[int], str | None]:
        return pages.pop(0)

    collected: list[int] = []
    async for page in AsyncPageIterator(fetch):
        collected.extend(page.items)
    assert collected == [10, 20]
