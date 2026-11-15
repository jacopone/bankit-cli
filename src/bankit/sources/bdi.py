"""Banca d'Italia, Base Dati Statistica, through the documented A2A export service.

Reference: BDS user guide (manuale_BDS_dic2019-ita.pdf), section 5.2 "Export dati con servizi A2A":
``https://a2a.bancaditalia.it/infostat/dataservices/export/{IT|EN}/CSV/{DATA|LEGEND|DOMAIN|STRUCTURE|ALL}
/{CUBE|PUBLICATION}/BANKITALIA/DIFF/<ID>`` answers with a zip of ';'-separated CSV files.

A publication's DATA zip holds one inner zip per statistical table; time-series tables are wide
(``DATA_OSS`` plus one column per series key). The same series can appear in several tables, some
of them no longer updated, so the table with the most recent observation wins.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..errors import NotFound, Rejected, SourceError, UsageError
from ..model import Observation, SearchHit, SeriesInfo
from ..periods import normalise_frequency, period_from_date
from ..transport import Response
from .base import Source, fold, in_range

BASE_URL = "https://a2a.bancaditalia.it/infostat/dataservices/export"

# Publication codes listed in the BDS user guide, section 5.2.
PUBLICATIONS = (
    "STABOL", "STAMEN", "STACORIS", "STAFINRA", "STAATER", "BAM", "MFN", "CFI", "BOP",
    "FPI", "FPR", "FPE", "SDDS", "STASDP", "IBF", "SST", "EXSTA",
)

_ZIP_MAGIC = b"PK\x03\x04"
_SUPPORT_ID = re.compile(rb"support ID is:\s*(\d+)")
_INNER_TS = re.compile(r"(\d{8}_\d{6})")
# Object-type label of a series row in EN and IT legends.
_SERIES_LABELS = {"Time series", "Serie storica"}


def export_url(lang: str, content: str, object_type: str, object_id: str) -> str:
    return f"{BASE_URL}/{lang.upper()}/CSV/{content}/{object_type}/BANKITALIA/DIFF/{object_id}"


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _check_zip(resp: Response) -> bytes:
    body = resp.content
    if body.startswith(_ZIP_MAGIC):
        return body
    m = _SUPPORT_ID.search(body)
    if m:
        raise Rejected(
            "request rejected by the Banca d'Italia firewall",
            url=resp.url,
            status=resp.status,
            support_id=m.group(1).decode(),
        )
    if resp.status in (400, 404):
        raise NotFound(f"not found at Banca d'Italia: {resp.url}", url=resp.url, status=resp.status)
    raise SourceError(
        f"unexpected response from Banca d'Italia (HTTP {resp.status}, {resp.content_type or 'no content type'})",
        url=resp.url,
        status=resp.status,
    )


def _parse_value(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(text: str) -> date:
    y, m, d = text.strip().replace("-", "/").split("/")
    return date(int(y), int(m), int(d))


def publication_of(key: str) -> str:
    pub = key.split("_", 1)[0].upper()
    if "_" not in key or not pub:
        raise UsageError(f"not a BdI series key (expected PUBLICATION_...): {key!r}", key=key)
    return pub


def frequency_of(key: str) -> str | None:
    """Second key segment is the frequency for most BdI keys; treat it as a hint only."""
    parts = key.split(".")
    return normalise_frequency(parts[1]) if len(parts) > 1 and len(parts[1]) == 1 else None


@dataclass
class _Table:
    name: str
    member: str
    generated: str
    header: list[str]
    rows: list[list[str]]


class BdiSource(Source):
    name = "bdi"

    def __init__(self, transport, lang: str = "en") -> None:
        super().__init__(transport, lang)
        self._tables: dict[str, tuple[Response, list[_Table]]] = {}
        self._legends: dict[str, tuple[Response, dict[str, str]]] = {}

    # -- downloads ---------------------------------------------------------------------------

    def _publication_tables(self, pub: str) -> tuple[Response, list[_Table]]:
        if pub not in self._tables:
            resp = self.transport.fetch(export_url("IT", "DATA", "PUBLICATION", pub))
            outer = zipfile.ZipFile(io.BytesIO(_check_zip(resp)))
            tables: list[_Table] = []
            for info in outer.infolist():
                raw = outer.read(info)
                members = (
                    [(n, zipfile.ZipFile(io.BytesIO(raw)).read(n)) for n in zipfile.ZipFile(io.BytesIO(raw)).namelist()]
                    if raw.startswith(_ZIP_MAGIC)
                    else [(info.filename, raw)]
                )
                for member, content in members:
                    if not member.lower().endswith(".csv"):
                        continue
                    reader = csv.reader(io.StringIO(_decode(content)), delimiter=";")
                    rows = list(reader)
                    if not rows or rows[0][:1] != ["DATA_OSS"] or "VALORE" in rows[0]:
                        continue  # not a wide time-series table (cube tables are long, with VALORE)
                    ts = _INNER_TS.search(member)
                    tables.append(
                        _Table(info.filename.removesuffix(".zip").removesuffix("_IT"), member,
                               ts.group(1) if ts else "", rows[0], rows[1:])
                    )
            self._tables[pub] = (resp, tables)
        return self._tables[pub]

    def _legend(self, pub: str) -> tuple[Response, dict[str, str]]:
        if pub not in self._legends:
            resp = self.transport.fetch(export_url(self.lang, "LEGEND", "PUBLICATION", pub))
            z = zipfile.ZipFile(io.BytesIO(_check_zip(resp)))
            titles: dict[str, str] = {}
            for name in z.namelist():
                for row in csv.reader(io.StringIO(_decode(z.read(name))), delimiter=";"):
                    if len(row) >= 3 and row[0] in _SERIES_LABELS:
                        titles[row[1]] = row[2]
            self._legends[pub] = (resp, titles)
        return self._legends[pub]

    # -- series ------------------------------------------------------------------------------

    def _series(self, key: str) -> tuple[Response, _Table, list[tuple[date, float]]]:
        pub = publication_of(key)
        resp, tables = self._publication_tables(pub)
        best: tuple[_Table, list[tuple[date, float]]] | None = None
        for t in tables:
            if key not in t.header:
                continue
            col = t.header.index(key)
            points = []
            for row in t.rows:
                if len(row) > col:
                    v = _parse_value(row[col])
                    if v is not None:
                        points.append((_parse_date(row[0]), v))
            if not points:
                continue
            points.sort()
            if best is None or (points[-1][0], t.generated) > (best[1][-1][0], best[0].generated):
                best = (t, points)
        if best is None:
            raise NotFound(f"series {key} not found in publication {pub}", key=key, publication=pub)
        return resp, best[0], best[1]

    def _title(self, key: str) -> str | None:
        try:
            return self._legend(publication_of(key))[1].get(key)
        except (NotFound, SourceError) as e:
            self.warnings.append({"warning": "legend_unavailable", "key": key, "detail": str(e)})
            return None

    def get(self, key: str, start: str | None = None, end: str | None = None) -> list[Observation]:
        resp, _table, points = self._series(key)
        freq = frequency_of(key)
        title = self._title(key)
        return [
            Observation(
                source=self.name,
                series_key=key,
                period=period_from_date(d, freq),
                date=d.isoformat(),
                value=v,
                title=title,
                unit=None,
                retrieved_at=resp.fetched_at,
                source_url=resp.url,
            )
            for d, v in points
            if in_range(d.isoformat(), start, end)
        ]

    def describe(self, key: str) -> SeriesInfo:
        resp, table, points = self._series(key)
        freq = frequency_of(key)
        return SeriesInfo(
            source=self.name,
            series_key=key,
            title=self._title(key),
            frequency=freq,
            unit=None,
            first_period=period_from_date(points[0][0], freq) or points[0][0].isoformat(),
            last_period=period_from_date(points[-1][0], freq) or points[-1][0].isoformat(),
            n_obs=len(points),
            source_url=resp.url,
            retrieved_at=resp.fetched_at,
            extra={"publication": publication_of(key), "table": table.name, "table_generated": table.generated},
        )

    def search(self, query: str, scope: Sequence[str] | None = None, limit: int = 50) -> list[SearchHit]:
        terms = fold(query).split()
        if not terms:
            raise UsageError("empty search query")
        explicit = scope is not None
        pubs = [p.upper() for p in scope] if explicit else list(PUBLICATIONS)
        hits: list[SearchHit] = []
        for pub in pubs:
            try:
                _resp, titles = self._legend(pub)
            except (NotFound, SourceError) as e:
                if explicit:
                    raise
                self.warnings.append({"warning": "publication_skipped", "publication": pub, "detail": str(e)})
                continue
            for key, title in titles.items():
                haystack = fold(f"{key} {title}")
                if all(t in haystack for t in terms):
                    hits.append(SearchHit(self.name, key, title, {"publication": pub}))
                    if len(hits) >= limit:
                        return hits
        return hits
