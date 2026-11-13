"""Bank for International Settlements (BIS) Data Portal, SDMX REST API v2 (``format=csv``).

Keys: ``FLOW/KEY`` (``WS_CBPOL/M.IT``) or ``FLOW.KEY`` (``WS_CBPOL.M.IT``), the dataflow id first.
SDMX key syntax is passed through (``M.XM+IT``, ``M.*``) and returns one series per matching key.
Series keys in the output use the ``FLOW.KEY`` form, built from the dimensions of the data structure.
``search`` lists the dataflows (there are about 30), not single series.

API documentation: https://stats.bis.org/api-doc/v2/
Terms of use: https://data.bis.org/help/legal (cite the BIS as the source; do not imply affiliation).
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
from collections.abc import Sequence

from ..errors import NotFound, SourceError, UsageError
from ..model import Observation, SearchHit, SeriesInfo
from ..periods import end_date_of_period, frequency_of_period, normalise_frequency
from ..transport import Response
from .base import Source, fold, in_range

BASE_URL = "https://stats.bis.org/api/v2"
AGENCY = "BIS"
VERSION = "~"  # latest stable version of the dataflow


def split_key(key: str) -> tuple[str, str]:
    if "/" in key:
        flow, rest = key.split("/", 1)
    elif "." in key:
        flow, rest = key.split(".", 1)
    else:
        raise UsageError(f"not a BIS key (expected FLOW/KEY, for example WS_CBPOL/M.IT): {key!r}", key=key)
    if not flow or not rest:
        raise UsageError(f"not a BIS key (expected FLOW/KEY, for example WS_CBPOL/M.IT): {key!r}", key=key)
    return flow.upper(), rest


def data_url(key: str, start: str | None = None, end: str | None = None) -> str:
    flow, rest = split_key(key)
    params = {"format": "csv"}
    if start:
        params["startPeriod"] = start
    if end:
        params["endPeriod"] = end
    return f"{BASE_URL}/data/dataflow/{AGENCY}/{flow}/{VERSION}/{rest}?{urllib.parse.urlencode(params)}"


def structure_url(flow: str) -> str:
    return f"{BASE_URL}/structure/dataflow/{AGENCY}/{flow}/{VERSION}?references=datastructure&format=sdmx-json"


def dataflows_url() -> str:
    return f"{BASE_URL}/structure/dataflow/{AGENCY}/*/{VERSION}?format=sdmx-json"


def unit_codelist_url() -> str:
    return f"{BASE_URL}/structure/codelist/{AGENCY}/CL_BIS_UNIT/{VERSION}?format=sdmx-json"


def _check(resp: Response, what: str) -> None:
    if resp.status == 404:
        raise NotFound(f"BIS: no {what} found: {resp.url}", url=resp.url)
    if not (200 <= resp.status < 300):
        raise SourceError(f"BIS answered HTTP {resp.status}", url=resp.url, status=resp.status)


def _json(resp: Response, what: str) -> dict:
    _check(resp, what)
    try:
        return json.loads(resp.content.decode("utf-8-sig"))["data"]
    except (ValueError, KeyError):
        raise SourceError(f"unexpected BIS response (not SDMX-JSON) for {what}", url=resp.url) from None


def _text(names: dict | None, fallback: str | None, lang: str) -> str | None:
    if names:
        return names.get(lang) or names.get("en") or next(iter(names.values()), fallback)
    return fallback


class BisSource(Source):
    name = "bis"

    def __init__(self, transport, lang: str = "en") -> None:
        super().__init__(transport, lang)
        self._dimensions: dict[str, list[str]] = {}
        self._units: dict[str, str] | None = None

    # -- metadata ----------------------------------------------------------------------------

    def _dimension_ids(self, flow: str) -> list[str]:
        if flow not in self._dimensions:
            data = _json(self.transport.fetch(structure_url(flow)), f"dataflow {flow}")
            try:
                dims = data["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"]
            except (KeyError, IndexError):
                raise SourceError(f"unexpected BIS data structure for {flow}", flow=flow) from None
            self._dimensions[flow] = [d["id"] for d in sorted(dims, key=lambda d: d.get("position", 0))]
        return self._dimensions[flow]

    def _unit_names(self) -> dict[str, str]:
        """UNIT_MEASURE code -> label. A failure is a warning: the code is used instead."""
        if self._units is None:
            try:
                data = _json(self.transport.fetch(unit_codelist_url()), "unit codelist")
                codes = data["codelists"][0]["codes"]
                self._units = {c["id"]: _text(c.get("names"), c.get("name"), self.lang) or c["id"] for c in codes}
            except (SourceError, NotFound, KeyError, IndexError) as e:
                self.warnings.append({"warning": "unit_labels_unavailable", "detail": str(e)})
                self._units = {}
        return self._units

    def _unit(self, code: str | None) -> str | None:
        if not code:
            return None
        return self._unit_names().get(code, code)

    # -- series ------------------------------------------------------------------------------

    def _fetch(self, key: str, start: str | None, end: str | None) -> tuple[Response, str, list[dict[str, str]]]:
        flow, _ = split_key(key)
        dims = self._dimension_ids(flow)
        resp = self.transport.fetch(data_url(key, start, end))
        _check(resp, "series")
        text = resp.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "TIME_PERIOD" not in reader.fieldnames or "OBS_VALUE" not in reader.fieldnames:
            raise SourceError("unexpected BIS response (not csv data)", url=resp.url)
        missing = [d for d in dims if d not in reader.fieldnames]
        if missing:
            raise SourceError(f"BIS response lacks the dimensions {missing}", url=resp.url)
        rows = list(reader)
        for r in rows:
            r["_KEY"] = f"{flow}." + ".".join(r[d] for d in dims)
        return resp, flow, rows

    def get(self, key: str, start: str | None = None, end: str | None = None) -> list[Observation]:
        resp, _flow, rows = self._fetch(key, start, end)
        out = []
        for r in rows:
            if not r.get("OBS_VALUE"):
                continue
            label = r["TIME_PERIOD"]
            d = end_date_of_period(label).isoformat()
            if not in_range(d, start, end):
                continue
            out.append(
                Observation(
                    source=self.name,
                    series_key=r["_KEY"],
                    period=label if frequency_of_period(label) else None,
                    date=d,
                    value=float(r["OBS_VALUE"]),
                    title=(r.get("TITLE") or "").strip() or None,
                    unit=self._unit(r.get("UNIT_MEASURE")),
                    retrieved_at=resp.fetched_at,
                    source_url=resp.url,
                )
            )
        return out

    def describe(self, key: str) -> SeriesInfo:
        resp, flow, rows = self._fetch(key, None, None)
        keys = sorted({r["_KEY"] for r in rows})
        if len(keys) != 1:
            raise UsageError(f"describe needs exactly one series; the key matches {len(keys)}", key=key, matches=keys[:20])
        obs = [r for r in rows if r.get("OBS_VALUE")]
        periods = sorted(r["TIME_PERIOD"] for r in obs)
        first = rows[0]
        return SeriesInfo(
            source=self.name,
            series_key=keys[0],
            title=(first.get("TITLE") or "").strip() or None,
            frequency=normalise_frequency(first.get("FREQ")),
            unit=self._unit(first.get("UNIT_MEASURE")),
            first_period=periods[0] if periods else None,
            last_period=periods[-1] if periods else None,
            n_obs=len(obs),
            source_url=resp.url,
            retrieved_at=resp.fetched_at,
            extra={
                "dataflow": flow,
                "unit_mult": first.get("UNIT_MULT") or None,
                "decimals": first.get("DECIMALS") or None,
                "source_ref": first.get("SOURCE_REF") or None,
                "compilation": first.get("COMPILATION") or None,
            },
        )

    # -- dataflows ---------------------------------------------------------------------------

    def search(self, query: str, scope: Sequence[str] | None = None, limit: int = 50) -> list[SearchHit]:
        """Find dataflows by words in their id or name; ``scope`` limits the search to given dataflow ids."""
        terms = fold(query).split()
        if not terms:
            raise UsageError("empty search query")
        data = _json(self.transport.fetch(dataflows_url()), "dataflows")
        wanted = {s.upper() for s in scope} if scope else None
        hits: list[SearchHit] = []
        for flow in data.get("dataflows", []):
            if wanted is not None and flow["id"].upper() not in wanted:
                continue
            title = _text(flow.get("names"), flow.get("name"), self.lang) or flow["id"]
            haystack = fold(f"{flow['id']} {title}")
            if all(t in haystack for t in terms):
                hits.append(SearchHit(self.name, flow["id"], title))
                if len(hits) >= limit:
                    break
        return hits
