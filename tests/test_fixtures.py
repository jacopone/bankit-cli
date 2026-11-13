"""The Banca d'Italia fixtures are synthetic and must stay equal to the generator's output."""

import importlib.util
import io
import json
import zipfile
from pathlib import Path

from .conftest import FIXTURES

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_fixtures.py"


def _generator():
    spec = importlib.util.spec_from_file_location("make_fixtures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flatten(raw: bytes, name: str = "") -> dict[str, bytes]:
    """Zip members by path, recursing into nested zips, so equality does not depend on compression."""
    if not raw.startswith(b"PK\x03\x04"):
        return {name: raw}
    out: dict[str, bytes] = {}
    z = zipfile.ZipFile(io.BytesIO(raw))
    for member in z.namelist():
        out.update(_flatten(z.read(member), f"{name}/{member}"))
    return out


def test_committed_bdi_fixtures_match_the_generator():
    built = _generator().build(FIXTURES / "ecb_MIR_IT_loans_nfc.csv")
    assert built
    for name, content in built.items():
        assert _flatten((FIXTURES / name).read_bytes(), name) == _flatten(content, name), name


def test_every_bdi_and_bis_fixture_is_listed_as_synthetic():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for prefix in ("bdi_", "bis_"):
        listed = {e["file"]: e for e in manifest.values() if e["file"].startswith(prefix)}
        assert listed and all(e.get("synthetic") is True for e in listed.values()), prefix
        assert {p.name for p in FIXTURES.glob(f"{prefix}*")} == set(listed), prefix
