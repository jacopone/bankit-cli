"""Record the ECB test fixture from the live ECB Data Portal.

The response is stored unmodified (the ECB reuse policy requires statistics and metadata to stay
unmodified and the source to be cited). Banca d'Italia fixtures are synthetic: see make_fixtures.py.
Updates the ECB entry of tests/fixtures/manifest.json (URL, file, HTTP status, content type, retrieval time).

Usage: python scripts/record_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bankit.sources import ecb  # noqa: E402
from bankit.transport import HttpTransport  # noqa: E402

OUT = ROOT / "tests" / "fixtures"

ECB = [
    (ecb.data_url("MIR/M.IT.B.A2A.A.R.A+0+1.2240.EUR.N", start="2003-01"), "ecb_MIR_IT_loans_nfc.csv"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    http = HttpTransport()
    for url, name in ECB:
        resp = http.fetch(url)
        (OUT / name).write_bytes(resp.content)
        manifest[url] = {
            "file": name,
            "status": resp.status,
            "content_type": resp.content_type,
            "fetched_at": resp.fetched_at,
        }
        print(f"{resp.status} {len(resp.content):>8} {name}")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
