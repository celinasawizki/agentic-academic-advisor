"""Ingest every undergraduate major, minor and certificate plus all undergraduate
courses from Temple's Academic Bulletin (bulletin.temple.edu).

Respects robots.txt (only program and /courses/ pages are fetched), waits 1s
between requests and caches pages locally. Output: data/temple/programs.json
and data/temple/courses.json with source URLs and retrieval timestamps.

    python -m scripts.ingest_bulletin            (from apps/api; re-parses cached pages)
    python -m scripts.ingest_bulletin --refresh  (re-crawl changed pages)
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.bulletin import clean, parse_course_blocks, parse_program_page, program_type  # noqa: E402
from scripts.http_cache import USER_AGENT, PoliteClient  # noqa: E402

BASE = "https://bulletin.temple.edu"
OUT = Path(__file__).resolve().parents[3] / "data" / "temple"
GENED = [  # From bulletin.temple.edu/undergraduate/general-education/ ("Program Framework")
    ("GW", "Analytical Reading & Writing", 1, "foundation"), ("GQ", "Quantitative Literacy", 1, "foundation"),
    ("GY", "Intellectual Heritage I", 1, "foundation"), ("GZ", "Intellectual Heritage II", 1, "foundation"),
    ("GA", "Arts", 1, "breadth"), ("GB", "Human Behavior", 1, "breadth"), ("GD", "Race & Diversity", 1, "breadth"),
    ("GG", "World Society", 1, "breadth"), ("GS", "Science & Technology", 2, "breadth"), ("GU", "U.S. Society", 1, "breadth"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(limit: int | None = None, refresh: bool = False) -> None:
    http = PoliteClient(delay=1.0)
    robots = RobotFileParser()
    robots.parse((http.get_text(f"{BASE}/robots.txt", use_cache=not refresh) or "").splitlines())
    sitemap = http.get_text(f"{BASE}/sitemap.xml", use_cache=not refresh) or ""
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap)

    program_urls = []
    for u in urls:
        m = re.match(rf"{BASE}/undergraduate/([^/]+)/([^/]+)/$", u)
        if m and program_type(m.group(2)) and "accelerated" not in m.group(1):
            program_urls.append((u, m.group(1), m.group(2)))
    course_urls = [u for u in urls if re.match(rf"{BASE}/courses/[a-z0-9-]+/$", u)]
    if limit:
        program_urls, course_urls = program_urls[:limit], course_urls[:limit]
    print(f"{len(program_urls)} program pages, {len(course_urls)} course subject pages")

    colleges: dict[str, str] = {}
    seen_ids: set[str] = set()
    programs = []
    for i, (url, college_slug, slug) in enumerate(program_urls, 1):
        if not robots.can_fetch(USER_AGENT, url):
            continue
        page = http.get_text(url)
        if not page:
            continue
        parsed = parse_program_page(page, url)
        if college_slug not in colleges:
            crumb = re.findall(r'<a href="/undergraduate/' + re.escape(college_slug) + r'/">(.*?)</a>', page)
            colleges[college_slug] = clean(crumb[0]) if crumb else college_slug.replace("-", " ").title()
        reqs = parsed["requirements"]
        pid = slug if slug not in seen_ids else f"{slug}-{college_slug}"
        seen_ids.add(pid)
        for j, r in enumerate(reqs, 1):
            r["id"] = f"{pid}-r{j}"
        programs.append({
            "id": pid, "name": parsed["title"], "type": program_type(slug), "college": colleges[college_slug],
            "catalog_year": parsed["catalog_year"], "source_url": url, "retrieved_at": now(),
            "total_credit_hours": parsed["total_credit_hours"], "requirements": reqs,
            "supported": any(r["kind"] in ("count", "credits") for r in reqs),
        })
        if i % 25 == 0:
            print(f"  programs {i}/{len(program_urls)}")

    years = [p["catalog_year"] for p in programs if p["catalog_year"]]
    bulletin_year = max(set(years), key=years.count) if years else None
    for p in programs:
        if not p["catalog_year"]:
            p["catalog_year"], p["catalog_year_inferred"] = bulletin_year, True
    programs.append({
        "id": "gened", "name": "General Education (GenEd)", "type": "gened", "college": "University",
        "catalog_year": next((p["catalog_year"] for p in programs if p["catalog_year"]), None),
        "source_url": f"{BASE}/undergraduate/general-education/", "retrieved_at": now(), "total_credit_hours": [],
        "supported": True,
        "requirements": [{"id": f"gened-{code.lower()}", "group": f"GenEd {tier.title()}", "name": f"{name} ({code})",
                          "kind": "count", "needed": n, "options": [], "patterns": [{"attribute": code}],
                          "notes": ["A GenEd course counts in one GenEd area only; minimum grade C-."],
                          "verification_status": "parsed"} for code, name, n, tier in GENED],
    })

    courses = {}
    for i, url in enumerate(course_urls, 1):
        if not robots.can_fetch(USER_AGENT, url):
            continue
        page = http.get_text(url)
        if not page:
            continue
        for c in parse_course_blocks(page):
            c["source_url"] = url
            courses[c["code"]] = c
        if i % 50 == 0:
            print(f"  course pages {i}/{len(course_urls)} ({len(courses)} undergraduate courses)")

    meta = {"source": "Temple University Academic Bulletin", "base_url": BASE, "generated_at": now(),
            "notice": "Parsed automatically from the public bulletin. Requirements are pending verification by an advisor."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "programs.json").write_text(json.dumps({"_meta": meta, "programs": programs}, indent=1))
    (OUT / "courses.json").write_text(json.dumps({"_meta": meta, "courses": sorted(courses.values(), key=lambda c: c["code"])}, indent=1))
    review = sum(r["verification_status"] == "needs_review" for p in programs for r in p["requirements"])
    print(f"Wrote {len(programs)} programs ({review} requirements need review) and {len(courses)} courses to {OUT}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--refresh"]
    main(int(args[0]) if args else None, refresh="--refresh" in sys.argv)
