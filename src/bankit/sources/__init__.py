"""Source registry and key routing."""

from __future__ import annotations

from ..errors import UsageError
from ..transport import Transport
from .base import Source
from .bdi import BdiSource
from .bis import BisSource
from .ecb import EcbSource

SOURCES: dict[str, type[Source]] = {"bdi": BdiSource, "ecb": EcbSource, "bis": BisSource}


def make_source(name: str, transport: Transport, lang: str = "en") -> Source:
    try:
        return SOURCES[name](transport, lang=lang)
    except KeyError:
        raise UsageError(f"unknown source {name!r}; available: {', '.join(SOURCES)}", source=name) from None


def route(key: str, source: str | None = None) -> tuple[str, str]:
    """Return (source name, bare key). An explicit ``bdi:``/``ecb:``/``bis:`` prefix wins over inference."""
    prefix, sep, rest = key.partition(":")
    if sep and prefix in SOURCES:
        if source and source != prefix:
            raise UsageError(f"key prefix {prefix!r} conflicts with --source {source!r}", key=key)
        return prefix, rest
    if source:
        return source, key
    # BIS dataflow ids start with WS_ (WS_CBPOL/M.IT). BdI keys start with PUBLICATION_FAMILY
    # (an underscore before the first dot); ECB keys are FLOW/KEY or FLOW.KEY with a plain flow id.
    if key.upper().startswith("WS_"):
        return "bis", key
    if "/" in key or "_" not in key.split(".", 1)[0]:
        return "ecb", key
    return "bdi", key


__all__ = ["SOURCES", "Source", "make_source", "route"]
