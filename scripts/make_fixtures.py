"""Generate the synthetic Banca d'Italia (BdI) and BIS test fixtures.

The files have the layout of the BDS A2A export (zips of ';'-separated, fully quoted CSV, decimal
comma, dates as YYYY/MM/DD, newest row first) but every value and every title is invented.
No Banca d'Italia data is stored in this repository's tests. For the BAM series from 2003-01 the
values are the ECB fixture value plus a small deterministic offset (at most 0.004), so the BdI-vs-ECB
consistency test keeps its meaning; earlier months and the MFN series come from a seeded generator.

The bis_* files reproduce the shape of the BIS SDMX REST API answers (dataflow list, data structure,
unit codelist, csv data) with invented names and values.

Output is deterministic. Writes tests/fixtures/bdi_*, bis_* and the BdI and BIS entries of manifest.json (ECB entries, recorded by record_fixtures.py, are kept as they are).

Usage: python scripts/make_fixtures.py [output_dir]
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bankit.sources import bdi, bis  # noqa: E402

DEFAULT_OUT = ROOT / "tests" / "fixtures"
FETCHED_AT = "2026-11-13T00:00:00+00:00"
ZIP_TIME = (2026, 1, 1, 0, 0, 0)

BAM_KEYS = {  # ECB AMOUNT_CAT -> BdI series key
    "A": "BAM_MIR.M.1300010.MIR5411.9.950.1000.SBI77.EUR.110.997",
    "0": "BAM_MIR.M.1300010.MIR5411.9.950.46.SBI77.EUR.110.997",
    "1": "BAM_MIR.M.1300010.MIR5411.9.950.47.SBI77.EUR.110.997",
}
BAM_TITLES = {
    "A": "Synthetic test series: loans to non-financial corporations, new business, total",
    "0": "Synthetic test series: loans to non-financial corporations, new business, up to EUR 1 million",
    "1": "Synthetic test series: loans to non-financial corporations, new business, over EUR 1 million",
}
MFN_KEYS = ["MFN_BMK.D.020.922.0.EUR.205", "MFN_BMK.D.020.922.0.EUR.210"]
MFN_TITLES = {
    "en": {
        MFN_KEYS[0]: "Synthetic test series: 5-year BTP benchmark yield",
        MFN_KEYS[1]: "Synthetic test series: 10-year BTP benchmark yield",
    },
    "it": {
        MFN_KEYS[0]: "Serie di prova (dati sintetici): rendimento BTP quinquennale",
        MFN_KEYS[1]: "Serie di prova (dati sintetici): rendimento BTP decennale",
    },
}


BIS_FLOWS = {
    "WS_CBPOL": "Synthetic test dataflow: central bank policy rates",
    "WS_EER": "Synthetic test dataflow: effective exchange rates",
    "WS_LONG_CPI": "Synthetic test dataflow: consumer prices",
}
BIS_COLUMNS = [
    "FREQ", "REF_AREA", "UNIT_MEASURE", "UNIT_MULT", "TIME_FORMAT", "COMPILATION", "DECIMALS",
    "SOURCE_REF", "SUPP_INFO_BREAKS", "TITLE", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "OBS_CONF", "OBS_PRE_BREAK",
]
BIS_AREAS = {"XM": "Euro area", "IT": "Italy"}


def _json(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _bis_csv(areas: list[str]) -> bytes:
    months = _month_ends(date(2024, 1, 1), date(2026, 8, 1))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(BIS_COLUMNS)
    for area in areas:
        level = 3.0 if area == "XM" else 2.4
        for i, d in enumerate(months):
            level = max(level - 0.25 * (i % 7 == 6), 0.5)  # a step down every seventh month
            value = "" if (area == "IT" and i == 3) else f"{level:g}"  # one missing observation
            w.writerow([
                "M", area, "368", "0", "", f"Synthetic compilation note, {area}", "4", "Synthetic test source", "",
                f" Synthetic test series: policy rate, {BIS_AREAS[area]}, monthly",
                d.strftime("%Y-%m"), value, "A" if value else "M", "F", "",
            ])
    return buf.getvalue().encode("utf-8")


def bis_files() -> dict[str, bytes]:
    flows = [{"id": k, "names": {"en": v}, "version": "1.0"} for k, v in BIS_FLOWS.items()]
    dims = [{"id": "FREQ", "position": 1}, {"id": "REF_AREA", "position": 2}]
    structure = {"data": {"dataflows": [flows[0]], "dataStructures": [
        {"id": "BIS_CBPOL", "dataStructureComponents": {"dimensionList": {"dimensions": dims}}}]}}
    units = {"data": {"codelists": [{"id": "CL_BIS_UNIT", "codes": [
        {"id": "368", "names": {"en": "Synthetic unit: per cent per year"}},
        {"id": "770", "names": {"en": "Synthetic unit: percentage of GDP"}}]}]}}
    return {
        "bis_dataflows.json": _json({"data": {"dataflows": flows}}),
        "bis_WS_CBPOL_structure.json": _json(structure),
        "bis_units.json": _json(units),
        "bis_WS_CBPOL_XM_IT.csv": _bis_csv(["XM", "IT"]),
        "bis_WS_CBPOL_XM.csv": _bis_csv(["XM"]),
    }


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def _zip(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in members:
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, content)
    return buf.getvalue()


def _num(value: float | None, decimals: int) -> str:
    return "" if value is None else f"{value:.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")


def _month_ends(first: date, last: date) -> list[date]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        out.append(nxt - timedelta(days=1))
        y, m = nxt.year, nxt.month
    return out


def _ecb_values(ecb_file: Path) -> dict[str, dict[str, float]]:
    """AMOUNT_CAT -> {YYYY-MM: value} from the recorded ECB fixture."""
    out: dict[str, dict[str, float]] = {}
    with ecb_file.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["AMOUNT_CAT"], {})[row["TIME_PERIOD"]] = float(row["OBS_VALUE"])
    return out


def bam_table(ecb_file: Path) -> bytes:
    ecb = _ecb_values(ecb_file)
    months = _month_ends(date(1995, 1, 1), date(2026, 8, 1))
    rng = random.Random(383)
    columns: dict[str, dict[date, float]] = {}
    for cat, key in BAM_KEYS.items():
        level = 9.0 - {"A": 0.0, "0": -0.6, "1": 0.8}[cat]
        series: dict[date, float] = {}
        for i, d in enumerate(months):
            ym = d.strftime("%Y-%m")
            if ym in ecb[cat]:
                offset = ((i * 7919 + len(key)) % 81 - 40) / 10000  # |offset| <= 0.004
                series[d] = round(ecb[cat][ym] + offset, 4)
            else:
                level += rng.uniform(-0.15, 0.1)
                series[d] = round(max(level, 1.0), 4)
        columns[key] = series
    keys = list(BAM_KEYS.values())
    rows = [["DATA_OSS", *keys]]
    for d in reversed(months):
        rows.append([d.strftime("%Y/%m/%d"), *(_num(columns[k][d], 4) for k in keys)])
    return _csv(rows)


def mfn_table(first: date, last: date) -> bytes:
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    rows = [["DATA_OSS", *MFN_KEYS]]
    for d in reversed(days):
        if d.weekday() >= 5:
            rows.append([d.strftime("%Y/%m/%d"), *[""] * len(MFN_KEYS)])
            continue
        t = (d - date(2016, 1, 1)).days / 365.25
        vals = [3.2 + 1.1 * math.sin(t / 2.1 + k) + 0.15 * math.sin(t * 9 + k) for k in range(len(MFN_KEYS))]
        rows.append([d.strftime("%Y/%m/%d"), *(_num(round(v, 5), 5) for v in vals)])
    return _csv(rows)


def legend(lang: str, publication: str, description: str, family: tuple[str, str], titles: dict[str, str]) -> bytes:
    if lang == "en":
        head, pub_label, fam_label, ts_label = ["Object Type", "Code", "Description"], "Publication", "Key Family", "Time series"
    else:
        head, pub_label, fam_label, ts_label = ["Tipologia di oggetto", "Codice", "Descrizione"], "Pubblicazione", "Famiglia", "Serie storica"
    rows = [head, [pub_label, publication, description], [fam_label, *family]]
    rows += [[ts_label, key, title] for key, title in titles.items()]
    return _csv(rows)


def build(ecb_file: Path) -> dict[str, bytes]:
    bam_data = _zip([("MIR0200_IT.zip", _zip([("20261007_000000-TIMESERIES-MULTICUBE.csv", bam_table(ecb_file))]))])
    mfn_data = _zip(
        [  # the stale table comes first, as in the real export
            ("TDEE0115_IT.zip", _zip([("20170215_000000-TIMESERIES-MULTICUBE.csv", mfn_table(date(2016, 1, 1), date(2017, 1, 31)))])),
            ("BMK0200_IT.zip", _zip([("20261009_000000-TIMESERIES-MULTICUBE.csv", mfn_table(date(2016, 1, 1), date(2026, 9, 30)))])),
        ]
    )
    legend_name = "20261009_000000-LEGEND-TIMESERIES-MULTICUBE.csv"
    bam_titles = {BAM_KEYS[c]: BAM_TITLES[c] for c in BAM_KEYS}
    return {
        "bdi_BAM_DATA_IT.zip": bam_data,
        "bdi_MFN_DATA_IT.zip": mfn_data,
        "bdi_BAM_LEGEND_EN.zip": _zip(
            [(legend_name, legend("en", "BAM", "Synthetic test publication", ("ATECO", "Serie di prova per attività economica"), bam_titles))]
        ),
        "bdi_MFN_LEGEND_EN.zip": _zip(
            [(legend_name, legend("en", "MFN", "Synthetic test publication", ("BMK", "Synthetic family: benchmark government bonds"), MFN_TITLES["en"]))]
        ),
        "bdi_MFN_LEGEND_IT.zip": _zip(
            [(legend_name, legend("it", "MFN", "Pubblicazione di prova sintetica", ("BMK", "Famiglia sintetica: titoli di Stato guida"), MFN_TITLES["it"]))]
        ),
        # Stand-ins for the firewall rejection page (HTTP 200 + HTML) and the invalid-object page (HTTP 400).
        "bdi_rejected.html": (
            b"<html><head><title>Request Rejected</title></head><body>The requested URL was rejected. "
            b"Please consult with your administrator.<br><br>Your support ID is: 1234567890123456789<br><br></body></html>\n"
        ),
        "bdi_invalid.html": b"<html><head><title>Bad request (synthetic test page)</title></head><body><h2>Bad request</h2></body></html>\n",
        **bis_files(),
    }


def manifest_entries() -> dict[str, dict[str, object]]:
    def entry(file: str, status: int, content_type: str) -> dict[str, object]:
        return {"file": file, "status": status, "content_type": content_type, "fetched_at": FETCHED_AT, "synthetic": True}

    zip_type = "application/zip"
    return {
        bdi.export_url("IT", "DATA", "PUBLICATION", "BAM"): entry("bdi_BAM_DATA_IT.zip", 200, zip_type),
        bdi.export_url("IT", "DATA", "PUBLICATION", "MFN"): entry("bdi_MFN_DATA_IT.zip", 200, zip_type),
        bdi.export_url("EN", "LEGEND", "PUBLICATION", "BAM"): entry("bdi_BAM_LEGEND_EN.zip", 200, zip_type),
        bdi.export_url("EN", "LEGEND", "PUBLICATION", "MFN"): entry("bdi_MFN_LEGEND_EN.zip", 200, zip_type),
        bdi.export_url("IT", "LEGEND", "PUBLICATION", "MFN"): entry("bdi_MFN_LEGEND_IT.zip", 200, zip_type),
        f"{bdi.BASE_URL}/IT/SDMXv21/DATAFLOW/BANKITALIA/DIFF": entry("bdi_rejected.html", 200, "text/html"),
        bdi.export_url("IT", "DATA", "PUBLICATION", "NOSUCHPUB"): entry("bdi_invalid.html", 400, "text/html"),
        bis.dataflows_url(): entry("bis_dataflows.json", 200, "application/json"),
        bis.structure_url("WS_CBPOL"): entry("bis_WS_CBPOL_structure.json", 200, "application/json"),
        bis.unit_codelist_url(): entry("bis_units.json", 200, "application/json"),
        bis.data_url("WS_CBPOL/M.XM+IT"): entry("bis_WS_CBPOL_XM_IT.csv", 200, "text/csv"),
        bis.data_url("WS_CBPOL/M.XM"): entry("bis_WS_CBPOL_XM.csv", 200, "text/csv"),
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    ecb_file = DEFAULT_OUT / "ecb_MIR_IT_loans_nfc.csv"
    for name, content in build(ecb_file).items():
        (out / name).write_bytes(content)
        print(f"{len(content):>8} {name}")
    manifest_path = out / "manifest.json"
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {u: e for u, e in existing.items() if e["file"].startswith("ecb_")}
    manifest.update(manifest_entries())
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
