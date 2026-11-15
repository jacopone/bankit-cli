"""Opt-in checks against the live sources: pytest -m live. Excluded from the default run and from CI."""

import pytest

from bankit.sources.bdi import BdiSource
from bankit.sources.ecb import EcbSource
from bankit.transport import HttpTransport

pytestmark = pytest.mark.live

LOANS_NFC = "BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997"


@pytest.fixture(autouse=True)
def _no_network():
    """Override the offline guard of conftest.py."""


def test_bdi_and_ecb_agree_up_to_rounding():
    http = HttpTransport()
    bdi = {o.period: o.value for o in BdiSource(http).get(LOANS_NFC, start="2024-01")}
    ecb = {o.period: o.value for o in EcbSource(http).get("MIR/M.IT.B.A2A.A.R.A.2240.EUR.N", start="2024-01")}
    common = set(bdi) & set(ecb)
    assert len(common) >= 12
    assert max(abs(bdi[p] - ecb[p]) for p in common) <= 0.005 + 1e-9


def test_bis_policy_rates_are_served():
    from bankit.sources.bis import BisSource  # noqa: PLC0415

    obs = BisSource(HttpTransport()).get("WS_CBPOL/M.XM", start="2024-01")
    assert obs and {o.series_key for o in obs} == {"WS_CBPOL.M.XM"}
    assert all(o.unit and o.title for o in obs)
