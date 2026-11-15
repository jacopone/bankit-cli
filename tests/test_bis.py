import pytest

from bankit.errors import NotFound, UsageError
from bankit.sources.bis import BisSource, data_url, split_key

from .conftest import FixtureTransport

KEYS = "WS_CBPOL/M.XM+IT"
ONE = "WS_CBPOL/M.XM"


def test_split_key_forms():
    assert split_key("ws_cbpol/M.IT") == ("WS_CBPOL", "M.IT")
    assert split_key("WS_CBPOL.M.IT") == ("WS_CBPOL", "M.IT")
    with pytest.raises(UsageError):
        split_key("WS_CBPOL")


def test_data_url():
    assert data_url(ONE, start="2024-01", end="2025-12") == (
        "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/~/M.XM?format=csv&startPeriod=2024-01&endPeriod=2025-12"
    )


def test_get_multi_key(transport):
    obs = BisSource(transport).get(KEYS)
    by_key = {}
    for o in obs:
        by_key.setdefault(o.series_key, []).append(o)
    assert set(by_key) == {"WS_CBPOL.M.XM", "WS_CBPOL.M.IT"}
    xm = by_key["WS_CBPOL.M.XM"]
    assert len(xm) == 32  # 2024-01 .. 2026-08
    assert (xm[-1].period, xm[-1].date, xm[-1].source) == ("2026-08", "2026-08-31", "bis")
    assert xm[-1].title == "Synthetic test series: policy rate, Euro area, monthly"  # stripped
    assert xm[-1].unit == "Synthetic unit: per cent per year"  # code 368 resolved
    assert xm[-1].source_url.startswith("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/")


def test_missing_observation_is_skipped(transport):
    it = [o for o in BisSource(transport).get(KEYS) if o.series_key == "WS_CBPOL.M.IT"]
    assert len(it) == 31


def test_period_filter():
    t = FixtureTransport(extra={data_url(ONE, start="2026-06"): data_url(ONE)})
    obs = BisSource(t).get(ONE, start="2026-06")
    assert [o.period for o in obs] == ["2026-06", "2026-07", "2026-08"]


def test_unit_codelist_failure_falls_back_to_the_code():
    t = FixtureTransport()
    del t.manifest[next(u for u in t.manifest if "CL_BIS_UNIT" in u)]
    src = BisSource(t)
    assert src.get(ONE)[0].unit == "368"
    assert src.warnings[0]["warning"] == "unit_labels_unavailable"


def test_describe(transport):
    info = BisSource(transport).describe(ONE)
    assert (info.series_key, info.frequency, info.n_obs) == ("WS_CBPOL.M.XM", "M", 32)
    assert (info.first_period, info.last_period) == ("2024-01", "2026-08")
    assert info.extra["dataflow"] == "WS_CBPOL"


def test_describe_needs_one_series():
    wildcard = "WS_CBPOL/M.*"
    t = FixtureTransport(extra={data_url(wildcard): data_url(KEYS)})
    with pytest.raises(UsageError) as e:
        BisSource(t).describe(wildcard)
    assert len(e.value.details["matches"]) == 2


def test_unknown_dataflow_is_not_found(transport):
    with pytest.raises(NotFound):
        BisSource(transport).get("WS_NOPE/M.XM")


def test_search_dataflows(transport):
    src = BisSource(transport)
    assert [h.series_key for h in src.search("POLICY rates")] == ["WS_CBPOL"]
    assert {h.series_key for h in src.search("synthetic")} == {"WS_CBPOL", "WS_EER", "WS_LONG_CPI"}
    assert [h.series_key for h in src.search("synthetic", scope=["ws_eer"])] == ["WS_EER"]
    assert len(src.search("synthetic", limit=2)) == 2
    assert src.search("no such words") == []
    with pytest.raises(UsageError):
        src.search("  ")
