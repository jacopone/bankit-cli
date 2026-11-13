"""bankit: Banca d'Italia statistics through interchangeable sources. Unofficial client."""

from __future__ import annotations

__version__ = "0.1.0"

from .api import describe, get, search, to_pandas  # noqa: E402

__all__ = ["__version__", "describe", "get", "search", "to_pandas"]
