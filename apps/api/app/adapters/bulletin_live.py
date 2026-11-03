"""Live access to Temple's public Academic Bulletin (bulletin.temple.edu) and
requirement-page search.

Fetching is polite: only bulletin.temple.edu, robots.txt respected, at most one
request per second across the process, an identifying User-Agent, and an on-disk
cache with a TTL so repeated plans don't re-hit Temple. If the network or the
page is unavailable, the page cached by the ingest crawl ("snapshot") is used and
labeled as such.

Search: Temple's bulletin search (/search/) is disallowed by robots.txt and
scraping Google violates its terms, so two providers are offered:
  * ClaudeWebSearch - Anthropic's web search tool restricted to bulletin.temple.edu
    (only the program name is sent; no student data). Used when an API key is set.
  * BulletinIndexSearch - ranks the bulletin's own sitemap (sitemap.xml) against
    the query. Deterministic, offline-capable fallback."""

import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

BASE = "https://bulletin.temple.edu"
USER_AGENT = "TempleAcademicPlanningPrototype/0.2 (student hackathon project; polite, 1 req/s, cached)"
_lock = threading.Lock()
_last_request = 0.0
_robots: tuple[float, RobotFileParser] | None = None


@dataclass
class FetchResult:
    url: str
    text: str | None
    mode: str  # live | cache | snapshot | unavailable
    retrieved_at: str | None
    status: int | None = None
    error: str | None = None
    sha: str | None = None


def _paths(url: str) -> tuple:
    key = hashlib.sha1(url.encode()).hexdigest() + ".html"
    return settings.data_dir / ".cache" / "live" / key, settings.data_dir / ".cache" / key


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


class BulletinFetcher:
    def __init__(self, live: bool | None = None):
        self.live = settings.live_bulletin_research if live is None else live
        self.results: list[FetchResult] = []

    def _robots(self, client: httpx.Client) -> RobotFileParser | None:
        global _robots
        if _robots and time.time() - _robots[0] < settings.bulletin_cache_ttl_hours * 3600:
            return _robots[1]
        rp = RobotFileParser()
        try:
            r = self._polite_get(client, f"{BASE}/robots.txt")
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except httpx.HTTPError:
            return None
        _robots = (time.time(), rp)
        return rp

    def _polite_get(self, client: httpx.Client, url: str) -> httpx.Response:
        global _last_request
        with _lock:
            gap = time.monotonic() - _last_request
            if gap < 1.0:
                time.sleep(1.0 - gap)
            _last_request = time.monotonic()
        return client.get(url)

    def get(self, url: str) -> FetchResult:
        url = url.split("#")[0]
        live_path, snap_path = _paths(url)
        res = self._get(url, live_path, snap_path)
        if res.text:
            res.sha = hashlib.sha256(res.text.encode()).hexdigest()[:16]
        self.results.append(res)
        return res

    def text(self, url: str) -> str | None:
        return self.get(url).text

    def _get(self, url: str, live_path, snap_path) -> FetchResult:
        if not url.startswith(BASE + "/"):
            return FetchResult(url, None, "unavailable", None, error="Only bulletin.temple.edu is fetched.")
        ttl = settings.bulletin_cache_ttl_hours * 3600
        if live_path.exists() and time.time() - live_path.stat().st_mtime < ttl:
            return FetchResult(url, live_path.read_text(), "cache", _iso(live_path.stat().st_mtime))
        error = None
        if self.live:
            try:
                with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=settings.bulletin_timeout_seconds,
                                  follow_redirects=True) as client:
                    robots = self._robots(client)
                    if robots is not None and not robots.can_fetch(USER_AGENT, url):
                        return FetchResult(url, None, "unavailable", None, error="Disallowed by robots.txt")
                    r = self._polite_get(client, url)
                if r.status_code == 200:
                    live_path.parent.mkdir(parents=True, exist_ok=True)
                    live_path.write_text(r.text)
                    return FetchResult(url, r.text, "live", _iso(time.time()), r.status_code)
                error = f"HTTP {r.status_code}"
            except httpx.HTTPError as e:
                error = f"{type(e).__name__}: {e}"
                log.warning("Bulletin fetch failed for %s: %s", url, error)
        else:
            error = "Live research disabled (LIVE_BULLETIN_RESEARCH=false)"
        if snap_path.exists():
            return FetchResult(url, snap_path.read_text(), "snapshot", _iso(snap_path.stat().st_mtime), error=error)
        return FetchResult(url, None, "unavailable", None, error=error)


@dataclass
class SearchHit:
    title: str
    url: str
    score: float | None = None


@dataclass
class SearchResult:
    query: str
    provider: str
    hits: list[SearchHit] = field(default_factory=list)
    error: str | None = None


STOP = {"requirements", "requirement", "temple", "university", "the", "of", "and", "in", "for", "program", "degree"}
TYPE_WORDS = {"major": {"ba", "bs", "bba", "bfa", "bm", "bsed", "bsn", "bsw", "bse"}, "minor": {"minor"}, "certificate": {"certificate"}}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP}


class BulletinIndexSearch:
    """Ranks undergraduate program pages in the bulletin's sitemap against the query."""

    name = "Temple Academic Bulletin index (sitemap.xml)"

    def __init__(self, fetcher: BulletinFetcher, known_titles: dict[str, str]):
        self.fetcher = fetcher
        self.titles = known_titles  # url -> program name, from the ingested catalog

    def search(self, query: str, program_type: str | None = None) -> SearchResult:
        sm = self.fetcher.get(f"{BASE}/sitemap.xml")
        urls = re.findall(r"<loc>([^<]+)</loc>", sm.text or "")
        if not urls:
            urls = list(self.titles)
        q = _tokens(query) | ({"minor"} if "minor" in query.lower() else set()) | ({"certificate"} if "certificate" in query.lower() else set())
        hits = []
        for u in urls:
            m = re.match(rf"{re.escape(BASE)}/undergraduate/[^/]+/([^/]+)/$", u)
            if not m:
                continue
            title = self.titles.get(u, m.group(1).replace("-", " ").title())
            words = _tokens(title) | _tokens(m.group(1))
            overlap = len(q & words)
            if not overlap:
                continue
            score = overlap / len(q | words)
            if program_type and TYPE_WORDS.get(program_type, set()) & words:
                score += 0.2
            hits.append(SearchHit(title, u, round(score, 3)))
        hits.sort(key=lambda h: -(h.score or 0))
        return SearchResult(query, self.name, hits[:5], None if hits else "No matching bulletin pages")


class ClaudeWebSearch:
    """Anthropic web search tool limited to bulletin.temple.edu. Only the query (a program
    name) is sent; never student records."""

    name = "Claude web search (bulletin.temple.edu only)"

    def search(self, query: str, program_type: str | None = None) -> SearchResult:
        from app.agents.llm import client
        c = client()
        if c is None:
            return SearchResult(query, self.name, error="No API key configured")
        try:
            resp = c.messages.create(
                model=settings.anthropic_model, max_tokens=2000,
                tools=[{"type": "web_search_20260209", "name": "web_search", "allowed_domains": ["bulletin.temple.edu"], "max_uses": 2}],
                messages=[{"role": "user", "content": f"Search the Temple University Academic Bulletin for: {query}. "
                                                      "Return the official undergraduate program requirements page."}],
            )
        except Exception as e:  # noqa: BLE001 - search is best effort; the index search is the fallback
            return SearchResult(query, self.name, error=f"{type(e).__name__}: {e}")
        hits = []
        for block in resp.content:
            if getattr(block, "type", "") == "web_search_tool_result" and isinstance(getattr(block, "content", None), list):
                for item in block.content:
                    url = getattr(item, "url", None)
                    if url and url.startswith(BASE):
                        hits.append(SearchHit(getattr(item, "title", url), url))
        return SearchResult(query, self.name, hits[:5], None if hits else "No bulletin results returned")
