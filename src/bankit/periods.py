"""Normalised periods, so that series from different sources join on the same label.

Labels: daily ``2026-09-30``, monthly ``2026-08``, quarterly ``2026-Q2``,
half-yearly ``2026-S1``, annual ``2026``.
"""

from __future__ import annotations

import calendar
import re
from datetime import date

FREQUENCIES = {"D", "M", "Q", "S", "A"}
# BdI uses H for half-yearly in some keys; SDMX uses S.
_ALIASES = {"H": "S", "Y": "A"}


def normalise_frequency(code: str | None) -> str | None:
    if not code:
        return None
    code = _ALIASES.get(code.upper(), code.upper())
    return code if code in FREQUENCIES else None


def period_from_date(d: date, frequency: str | None) -> str | None:
    """Period label for an observation date; None when the frequency is unknown."""
    if frequency == "D":
        return d.isoformat()
    if frequency == "M":
        return f"{d.year:04d}-{d.month:02d}"
    if frequency == "Q":
        return f"{d.year:04d}-Q{(d.month - 1) // 3 + 1}"
    if frequency == "S":
        return f"{d.year:04d}-S{1 if d.month <= 6 else 2}"
    if frequency == "A":
        return f"{d.year:04d}"
    return None


_PERIOD_RE = re.compile(
    r"^(?P<y>\d{4})(?:-(?:(?P<m>\d{2})(?:-(?P<d>\d{2}))?|Q(?P<q>[1-4])|S(?P<s>[12])|W\d{2}))?$"
)


def end_date_of_period(label: str) -> date:
    """Last calendar day of an SDMX-style period label (used when a source gives no date)."""
    m = _PERIOD_RE.match(label)
    if not m:
        raise ValueError(f"unrecognised period: {label!r}")
    y = int(m["y"])
    if m["d"]:
        return date(y, int(m["m"]), int(m["d"]))
    if m["m"]:
        month = int(m["m"])
    elif m["q"]:
        month = int(m["q"]) * 3
    elif m["s"]:
        month = int(m["s"]) * 6
    else:
        month = 12
    return date(y, month, calendar.monthrange(y, month)[1])


def frequency_of_period(label: str) -> str | None:
    m = _PERIOD_RE.match(label)
    if not m:
        return None
    if m["d"]:
        return "D"
    if m["m"]:
        return "M"
    if m["q"]:
        return "Q"
    if m["s"]:
        return "S"
    if "W" in label:
        return None
    return "A"
