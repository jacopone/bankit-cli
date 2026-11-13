import csv
import io
import json

import pytest

import bankit.cli as cli
from bankit.sources import route

from .conftest import FixtureTransport

LOANS_NFC = "BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997"


@pytest.fixture
def run(monkeypatch, tmp_path, capsys):
    """Run the CLI with fixtures behind the cache; returns (exit code, stdout, stderr)."""
    recorded = "https://data-api.ecb.europa.eu/service/data/MIR/M.IT.B.A2A.A.R.A+0+1.2240.EUR.N?format=csvdata&startPeriod=2003-01"
    fixtures = FixtureTransport(extra={recorded.replace("2003-01", "2026-08"): recorded})

    original = cli.CachingTransport

    def caching(**kwargs):
        kwargs["cache_dir"] = kwargs.get("cache_dir") or tmp_path / "cache"
        return original(inner=fixtures, **kwargs)

    monkeypatch.setattr(cli, "CachingTransport", caching)

    def _run(*argv):
        code = cli.run(list(argv))
        out, err = capsys.readouterr()
        return code, out, err

    return _run


def test_get_csv(run):
    code, out, err = run("get", LOANS_NFC, "--start", "2026-07")
    assert code == 0, err
    rows = list(csv.DictReader(io.StringIO(out)))
    assert list(rows[0]) == list(cli.OBSERVATION_FIELDS)
    assert [(r["period"], r["value"]) for r in rows] == [("2026-07", "3.786"), ("2026-08", "3.7122")]


def test_get_two_sources_one_schema(run):
    code, out, err = run("get", LOANS_NFC, "ecb:MIR/M.IT.B.A2A.A.R.A+0+1.2240.EUR.N", "--start", "2026-08", "--format", "json")
    assert code == 0, err
    rows = json.loads(out)
    assert {r["source"] for r in rows} == {"bdi", "ecb"}


def test_describe_json(run):
    code, out, _ = run("describe", LOANS_NFC)
    assert code == 0
    info = json.loads(out)
    assert info["last_period"] == "2026-08" and info["extra"]["table"] == "MIR0200"


def test_search_csv(run):
    code, out, _ = run("search", "loans non-financial corporations new business total", "--publication", "BAM")
    assert code == 0
    assert LOANS_NFC in out


@pytest.mark.parametrize(
    ("argv", "exit_status", "error"),
    [
        (("search", "loans", "--source", "ecb"), 3, "unsupported"),
        (("get", "BAM_MIR.M.0000000.NOPE"), 4, "not_found"),
        (("get", "NOTAKEY"), 2, "usage"),
        (("get",), 2, "usage"),
    ],
)
def test_errors_are_json_with_exit_codes(run, argv, exit_status, error):
    if argv == ("get",):
        with pytest.raises(SystemExit) as e:
            run(*argv)
        assert e.value.code == exit_status
        return
    code, out, err = run(*argv)
    assert code == exit_status
    assert out == ""
    assert json.loads(err.strip().splitlines()[-1])["error"] == error


def test_offline_cache_miss(run):
    code, _, err = run("get", LOANS_NFC, "--offline")
    assert code == 6
    assert json.loads(err)["error"] == "offline_cache_miss"


def test_offline_after_cached(run):
    assert run("get", LOANS_NFC)[0] == 0
    code, out, _ = run("get", LOANS_NFC, "--offline", "--start", "2026-08")
    assert code == 0 and "3.7122" in out


def test_route():
    assert route(LOANS_NFC) == ("bdi", LOANS_NFC)
    assert route("MIR/M.IT.B") == ("ecb", "MIR/M.IT.B")
    assert route("MIR.M.IT.B") == ("ecb", "MIR.M.IT.B")
    assert route("ecb:MIR.M.IT.B") == ("ecb", "MIR.M.IT.B")
    assert route("bdi:" + LOANS_NFC) == ("bdi", LOANS_NFC)


def test_untrusted_certificate_hints_at_ssl_cert_file(monkeypatch):
    import ssl  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415

    from bankit.errors import SourceError  # noqa: PLC0415
    from bankit.transport import HttpTransport  # noqa: PLC0415

    def refuse(*args, **kwargs):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("self-signed certificate in certificate chain"))

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(SourceError) as e:
        HttpTransport().fetch("https://example.invalid/x")
    assert "SSL_CERT_FILE" in str(e.value)
