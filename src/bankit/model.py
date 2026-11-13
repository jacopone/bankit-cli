"""Source-independent output types. Every adapter returns these."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

OBSERVATION_FIELDS = (
    "source",
    "series_key",
    "period",
    "date",
    "value",
    "title",
    "unit",
    "retrieved_at",
    "source_url",
)


@dataclass(frozen=True)
class Observation:
    source: str
    series_key: str
    period: str | None
    date: str
    value: float
    title: str | None
    unit: str | None
    retrieved_at: str
    source_url: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SeriesInfo:
    source: str
    series_key: str
    title: str | None
    frequency: str | None
    unit: str | None
    first_period: str | None
    last_period: str | None
    n_obs: int
    source_url: str
    retrieved_at: str
    extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SearchHit:
    source: str
    series_key: str
    title: str
    extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
