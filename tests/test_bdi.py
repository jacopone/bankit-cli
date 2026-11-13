import io
import zipfile

import pytest

from bankit.errors import NotFound, Rejected, UsageError
from bankit.sources.bdi import BdiSource, _check_zip, _decode, export_url, frequency_of

from .conftest import FixtureTransport

LOANS_NFC = "BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997"
BTP10 = "MFN_BMK.D.020.922.0.EUR.210"


def test_get_monthly_series(transport):
    obs = BdiSource(transport).get(LOANS_NFC)
    assert len(obs) == 380
    assert (obs[0].period, obs[0].date) == ("1995-01", "1995-01-31")
    last = obs[-1]
    assert (last.period, last.date, last.value) == ("2026-08", "2026-08-31", 3.7122)
    assert last.title == "Synthetic test series: loans to non-financial corporations, new business, total"
    assert last.source == "bdi" and last.source_url.endswith("/DATA/PUBLICATION/BANKITALIA/DIFF/BAM")


def test_get_filters_by_period_prefix(transport):
    obs = BdiSource(transport).get(LOANS_NFC, start="2026-01", end="2026-03")
    assert [o.period for o in obs] == ["2026-01", "2026-02", "2026-03"]


def test_series_in_two_tables_uses_the_current_one(transport):
    # MFN_BMK.D.* is in TDEE0115 (stale, ends 2017-01-31, listed first) and BMK0200 (current).
    src = BdiSource(transport)
    obs = src.get(BTP10)
    assert obs[-1].date == "2026-09-30"
    assert obs[-1].value == 2.9703
    assert obs[-1].period == "2026-09-30"
    assert src.describe(BTP10).extra["table"] == "BMK0200"


def test_legend_is_decoded_as_utf8(transport):
    # The files are UTF-8: the ATECO key family reads "attività", never the mojibake "attivitÃ ".
    resp = transport.fetch(export_url("EN", "LEGEND", "PUBLICATION", "BAM"))
    z = zipfile.ZipFile(io.BytesIO(_check_zip(resp)))
    text = _decode(z.read(z.namelist()[0]))
    assert "Serie di prova per attività economica" in text
    assert "attivitÃ" not in text
    assert BdiSource(transport)._legend("BAM")[1]  # time-series titles parsed


def test_italian_legend(transport):
    src = BdiSource(transport, lang="it")
    hits = src.search("rendimento btp decennale", scope=["MFN"])
    assert {h.series_key for h in hits} >= {BTP10}
    assert src.get(BTP10, start="2026-09-30")[0].title == "Serie di prova (dati sintetici): rendimento BTP decennale"


def test_rejection_is_not_cached(tmp_path):
    from bankit.transport import CachingTransport  # noqa: PLC0415

    url = export_url("IT", "DATA", "PUBLICATION", "BAM")
    inner = FixtureTransport(extra={url: "https://a2a.bancaditalia.it/infostat/dataservices/export/IT/SDMXv21/DATAFLOW/BANKITALIA/DIFF"})
    cached = CachingTransport(inner=inner, cache_dir=tmp_path)
    for _ in range(2):
        with pytest.raises(Rejected):
            BdiSource(cached).get(LOANS_NFC)
    assert inner.calls.count(url) == 2
    assert not list(tmp_path.iterdir())


def test_describe(transport):
    info = BdiSource(transport).describe(LOANS_NFC)
    assert info.frequency == "M"
    assert (info.first_period, info.last_period, info.n_obs) == ("1995-01", "2026-08", 380)
    assert info.extra == {"publication": "BAM", "table": "MIR0200", "table_generated": info.extra["table_generated"]}


def test_search(transport):
    hits = BdiSource(transport).search("loans non-financial corporations new business total", scope=["BAM"])
    keys = {h.series_key for h in hits}
    assert LOANS_NFC in keys
    assert all(h.extra["publication"] == "BAM" for h in hits)


def test_search_is_accent_and_case_insensitive(transport):
    assert BdiSource(transport).search("BTP 10-YEAR", scope=["MFN"])


def test_firewall_rejection_is_an_error_not_data():
    url = export_url("IT", "DATA", "PUBLICATION", "BAM")
    t = FixtureTransport(extra={url: "https://a2a.bancaditalia.it/infostat/dataservices/export/IT/SDMXv21/DATAFLOW/BANKITALIA/DIFF"})
    with pytest.raises(Rejected) as e:
        BdiSource(t).get(LOANS_NFC)
    assert e.value.details["status"] == 200
    assert e.value.details["support_id"].isdigit()


def test_invalid_publication_is_not_found(transport):
    url = export_url("IT", "DATA", "PUBLICATION", "NOSUCHPUB")
    assert url in transport.manifest
    with pytest.raises(NotFound):
        BdiSource(transport).get("NOSUCHPUB_X.M.1")


def test_unknown_series_in_known_publication(transport):
    with pytest.raises(NotFound):
        BdiSource(transport).get("BAM_MIR.M.0000000.NOPE")


def test_key_without_publication_prefix():
    with pytest.raises(UsageError):
        BdiSource(FixtureTransport()).get("MIR5411")


def test_frequency_hint():
    assert frequency_of(LOANS_NFC) == "M"
    assert frequency_of(BTP10) == "D"
    assert frequency_of("MFN_BOT.24.001.20.917") is None
