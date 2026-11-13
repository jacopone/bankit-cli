"""The interface every data source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..errors import Unsupported
from ..model import Observation, SearchHit, SeriesInfo
from ..transport import Transport


class Source(ABC):
    name: str = ""

    def __init__(self, transport: Transport, lang: str = "en") -> None:
        self.transport = transport
        self.lang = lang
        self.warnings: list[dict[str, object]] = []

    @abstractmethod
    def get(self, key: str, start: str | None = None, end: str | None = None) -> list[Observation]: ...

    @abstractmethod
    def describe(self, key: str) -> SeriesInfo: ...

    def search(self, query: str, scope: Sequence[str] | None = None, limit: int = 50) -> list[SearchHit]:
        raise Unsupported(f"source '{self.name}' does not support search", source=self.name)


def in_range(period_or_date: str, start: str | None, end: str | None) -> bool:
    """Prefix comparison: '2024-01' keeps 2024-01-xx, '2024' keeps the whole year."""
    if start and period_or_date[: len(start)] < start:
        return False
    if end and period_or_date[: len(end)] > end:
        return False
    return True
