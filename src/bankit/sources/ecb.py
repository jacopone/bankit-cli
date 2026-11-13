"""European Central Bank Data Portal, SDMX 2.1 REST API (``format=csvdata``).

Keys: ``FLOW/KEY`` (``MIR/M.IT.B.A2A.A.R.A.2240.EUR.N``) or the ``FLOW.KEY`` form used in the KEY
column of ECB files. SDMX key syntax is passed through, so ``A+0+1`` and wildcards work and return
one series per matching key.
"""

from __future__ import annotations

import csv
import io
import urllib.parse

from ..errors import NotFound, Rejected, SourceError, UsageError
from ..model import Observation, SeriesInfo
from ..periods import end_date_of_period, frequency_of_period, normalise_frequency
from ..transport import Response
from .base import Source, in_range

BASE_URL = "https://data-api.ecb.europa.eu/service"


def split_key(key: str) -> tuple[str, str]:
    if "/" in key:
        flow, rest = key.split("/", 1)
    elif "." in key:
        flow, rest = key.split(".", 1)
    else:
        raise UsageError(f"not an ECB key (expected FLOW/KEY): {key!r}", key=key)
    if not flow or not rest:
        raise UsageError(f"not an ECB key (expected FLOW/KEY): {key!r}", key=key)
    return flow.upper(), rest


def data_url(key: str, start: str | None = None, end: str | None = None) -> str:
    flow, rest = split_key(key)
    params = {"format": "csvdata"}
    if start:
        params["startPeriod"] = start
    if end:
        params["endPeriod"] = end
    return f"{BASE_URL}/data/{flow}/{rest}?{urllib.parse.urlencode(params)}"


def _rows(resp: Response) -> list[dict[str, str]]:
    if resp.status == 404:
        raise NotFound(f"no ECB series match: {resp.url}", url=resp.url)
    if not (200 <= resp.status < 300):
        raise SourceError(f"ECB answered HTTP {resp.status}", url=resp.url, status=resp.status)
    text = resp.content.decode("utf-8-sig")
    if not text.startswith("KEY,"):
        if "Request Rejected" in text:
            raise Rejected("request rejected by the ECB firewall", url=resp.url)
        raise SourceError("unexpected ECB response (not csvdata)", url=resp.url)
    return list(csv.DictReader(io.StringIO(text)))


class EcbSource(Source):
    name = "ecb"

    def _fetch(self, key: str, start: str | None, end: str | None) -> tuple[Response, list[dict[str, str]]]:
        resp = self.transport.fetch(data_url(key, start, end))
        return resp, _rows(resp)

    def get(self, key: str, start: str | None = None, end: str | None = None) -> list[Observation]:
        resp, rows = self._fetch(key, start, end)
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
                    series_key=r["KEY"],
                    period=label if frequency_of_period(label) else None,
                    date=d,
                    value=float(r["OBS_VALUE"]),
                    title=r.get("TITLE") or None,
                    unit=r.get("UNIT") or None,
                    retrieved_at=resp.fetched_at,
                    source_url=resp.url,
                )
            )
        return out

    def describe(self, key: str) -> SeriesInfo:
        resp, rows = self._fetch(key, None, None)
        keys = sorted({r["KEY"] for r in rows})
        if len(keys) != 1:
            raise UsageError(f"describe needs exactly one series; the key matches {len(keys)}", key=key, matches=keys[:20])
        obs = [r for r in rows if r.get("OBS_VALUE")]
        periods = sorted(r["TIME_PERIOD"] for r in obs)
        first = rows[0]
        return SeriesInfo(
            source=self.name,
            series_key=keys[0],
            title=first.get("TITLE") or None,
            frequency=normalise_frequency(first.get("FREQ")),
            unit=first.get("UNIT") or None,
            first_period=periods[0] if periods else None,
            last_period=periods[-1] if periods else None,
            n_obs=len(obs),
            source_url=resp.url,
            retrieved_at=resp.fetched_at,
            extra={
                "title_compl": first.get("TITLE_COMPL") or None,
                "unit_mult": first.get("UNIT_MULT") or None,
                "decimals": first.get("DECIMALS") or None,
                "source_agency": first.get("SOURCE_AGENCY") or None,
            },
        )
