"""HTTP transport with an on-disk cache. Adapters receive a transport, tests inject a fake."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from . import __version__
from .errors import NotFound, OfflineMiss, SourceError

USER_AGENT = f"bankit-cli/{__version__} (unofficial client)"


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    content_type: str
    content: bytes
    fetched_at: str


class Transport(Protocol):
    def fetch(self, url: str) -> Response: ...


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class HttpTransport:
    """Single attempt per request, no retries: a failed call is reported, not repeated."""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> Response:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Response(url, r.status, r.headers.get("Content-Type", ""), r.read(), _now())
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            if e.code == 404:
                raise NotFound(f"not found at source: {url}", url=url, status=404) from None
            return Response(url, e.code, e.headers.get("Content-Type", "") if e.headers else "", body, _now())
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SourceError(f"network error: {e}", url=url) from None


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "bankit"


class CachingTransport:
    """Caches successful (2xx) data responses by URL. ``offline`` never touches the network.

    HTML is never cached: sources answer firewall rejections with HTTP 200 and an HTML page,
    and a cached rejection would be replayed until the cache expires.
    """

    def __init__(
        self,
        inner: Transport | None = None,
        cache_dir: Path | None = None,
        ttl_seconds: int = 24 * 3600,
        offline: bool = False,
        refresh: bool = False,
    ) -> None:
        self.inner = inner or HttpTransport()
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self.ttl_seconds = ttl_seconds
        self.offline = offline
        self.refresh = refresh

    def _paths(self, url: str) -> tuple[Path, Path]:
        h = hashlib.sha256(url.encode()).hexdigest()[:32]
        return self.cache_dir / f"{h}.bin", self.cache_dir / f"{h}.json"

    def fetch(self, url: str) -> Response:
        data_path, meta_path = self._paths(url)
        if meta_path.exists() and data_path.exists() and not self.refresh:
            meta = json.loads(meta_path.read_text())
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["fetched_at"])).total_seconds()
            if self.offline or age < self.ttl_seconds:
                return Response(url, meta["status"], meta["content_type"], data_path.read_bytes(), meta["fetched_at"])
        if self.offline:
            raise OfflineMiss(f"not in cache (offline): {url}", url=url)
        resp = self.inner.fetch(url)
        if 200 <= resp.status < 300 and not resp.content_type.lower().startswith("text/html"):
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            data_path.write_bytes(resp.content)
            meta_path.write_text(
                json.dumps(
                    {"url": url, "status": resp.status, "content_type": resp.content_type, "fetched_at": resp.fetched_at}
                )
            )
        return resp
