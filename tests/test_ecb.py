import pytest

from bankit.errors import Unsupported, UsageError
from bankit.sources.ecb import EcbSource, data_url, split_key

from .conftest import FixtureTransport

KEYS = "MIR/M.IT.B.A2A.A.R.A+0+1.2240.EUR.N"


def test_split_key_forms():
    assert split_key("MIR/M.IT.B") == ("MIR", "M.IT.B")
    assert split_key("MIR.M.IT.B") == ("MIR", "M.IT.B")
    with pytest.raises(UsageError):
        split_key("MIR")


def test_data_url():
    assert data_url(KEYS, start="2003-01") == (
        "https://data-api.ecb.europa.eu/service/data/MIR/M.IT.B.A2A.A.R.A+0+1.2240.EUR.N?format=csvdata&startPeriod=2003-01"
    )


def test_get_multi_key(transport):
    obs = EcbSource(transport).get(KEYS, start="2003-01")
    by_key = {}
    for o in obs:
        by_key.setdefault(o.series_key, []).append(o)
    assert set(by_key) == {f"MIR.M.IT.B.A2A.A.R.{c}.2240.EUR.N" for c in "A01"}
    total = by_key["MIR.M.IT.B.A2A.A.R.A.2240.EUR.N"]
    assert len(total) == 284
    assert (total[-1].period, total[-1].date, total[-1].value) == ("2026-08", "2026-08-31", 3.71)
    assert total[-1].title == "Bank interest rates on loans to corporations (new business)"
    assert total[-1].unit == "PCPA"


def test_describe_needs_one_series():
    recorded = data_url(KEYS, start="2003-01")
    t = FixtureTransport(extra={data_url(KEYS): recorded})
    with pytest.raises(UsageError) as e:
        EcbSource(t).describe(KEYS)
    assert len(e.value.details["matches"]) == 3


def test_search_is_unsupported(transport):
    with pytest.raises(Unsupported):
        EcbSource(transport).search("loans")
