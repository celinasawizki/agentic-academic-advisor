"""Polite fetcher: identifies itself, waits between requests, caches responses
on disk (data/temple/.cache, gitignored) so re-runs never re-hit Temple."""

import hashlib
import time
from pathlib import Path

import httpx

USER_AGENT = "TempleAcademicPlanningPrototype/0.1 (student hackathon project; polite crawler, 1 req/s)"
CACHE = Path(__file__).resolve().parents[3] / "data" / "temple" / ".cache"


class PoliteClient:
    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.last = 0.0
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)
        CACHE.mkdir(parents=True, exist_ok=True)

    def _wait(self):
        gap = time.monotonic() - self.last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self.last = time.monotonic()

    def get_text(self, url: str, use_cache: bool = True) -> str | None:
        path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html")
        if use_cache and path.exists():
            return path.read_text()
        if not use_cache and path.exists():
            path.unlink()
        for attempt in range(3):
            self._wait()
            try:
                r = self.client.get(url)
            except httpx.HTTPError:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                path.write_text(r.text)
                return r.text
            if r.status_code == 404:
                return None
            time.sleep(5 * (attempt + 1))
        return None

    def raw(self) -> httpx.Client:
        return self.client

    def throttle(self):
        self._wait()
