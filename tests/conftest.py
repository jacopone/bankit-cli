from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from bankit.errors import NotFound
from bankit.transport import Response

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("network access in tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class FixtureTransport:
    """Serves recorded responses by URL; extra entries map URLs to other recorded files."""

    def __init__(self, extra: dict[str, str] | None = None) -> None:
        self.manifest = json.loads((FIXTURES / "manifest.json").read_text())
        for url, recorded_url in (extra or {}).items():
            self.manifest[url] = self.manifest[recorded_url]
        self.calls: list[str] = []

    def fetch(self, url: str) -> Response:
        self.calls.append(url)
        entry = self.manifest.get(url)
        if entry is None:
            raise NotFound(f"no fixture for {url}", url=url)
        return Response(
            url, entry["status"], entry["content_type"], (FIXTURES / entry["file"]).read_bytes(), entry["fetched_at"]
        )


@pytest.fixture
def transport() -> FixtureTransport:
    return FixtureTransport()
