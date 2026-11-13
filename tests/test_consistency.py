"""BdI and ECB publish the same harmonised Italian series; values must agree up to rounding."""

from bankit.sources.bdi import BdiSource
from bankit.sources.ecb import EcbSource

# BdI amount class (key segment 7) -> ECB AMOUNT_CAT, verified 2026-10-23.
PAIRS = {
    "1000": "A",  # total
    "46": "0",  # up to EUR 1 million
    "47": "1",  # over EUR 1 million
}


def test_loans_to_nfc_bdi_vs_ecb(transport):
    ecb = EcbSource(transport).get("MIR/M.IT.B.A2A.A.R.A+0+1.2240.EUR.N", start="2003-01")
    bdi = BdiSource(transport)
    for bdi_amount, ecb_amount in PAIRS.items():
        b = {o.period: o.value for o in bdi.get(f"BAM_MIR.M.1300010.MIR5411.9.950.{bdi_amount}.SBI77.EUR.110.997")}
        e = {o.period: o.value for o in ecb if o.series_key == f"MIR.M.IT.B.A2A.A.R.{ecb_amount}.2240.EUR.N"}
        common = set(b) & set(e)
        assert len(common) == 284
        assert max(abs(b[p] - e[p]) for p in common) <= 0.005 + 1e-9  # ECB rounds to 2 decimals
