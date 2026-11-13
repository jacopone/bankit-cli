"""Library entry points; the CLI is a thin layer over these."""

from __future__ import annotations

from collections.abc import Sequence

from .model import OBSERVATION_FIELDS, Observation, SearchHit, SeriesInfo
from .sources import make_source, route
from .transport import CachingTransport, Transport


def _transport(transport: Transport | None) -> Transport:
    return transport or CachingTransport()


def get(
    key: str,
    start: str | None = None,
    end: str | None = None,
    source: str | None = None,
    lang: str = "en",
    transport: Transport | None = None,
) -> list[Observation]:
    name, bare = route(key, source)
    return make_source(name, _transport(transport), lang).get(bare, start, end)


def describe(
    key: str, source: str | None = None, lang: str = "en", transport: Transport | None = None
) -> SeriesInfo:
    name, bare = route(key, source)
    return make_source(name, _transport(transport), lang).describe(bare)


def search(
    query: str,
    source: str = "bdi",
    scope: Sequence[str] | None = None,
    limit: int = 50,
    lang: str = "en",
    transport: Transport | None = None,
) -> list[SearchHit]:
    return make_source(source, _transport(transport), lang).search(query, scope, limit)


def to_pandas(rows: Sequence[Observation]):
    try:
        import pandas as pd
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError("to_pandas needs the optional dependency: pip install 'bankit-cli[pandas]'") from e
    return pd.DataFrame([r.to_dict() for r in rows], columns=list(OBSERVATION_FIELDS))
