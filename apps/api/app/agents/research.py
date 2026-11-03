import json
from collections import Counter

from app.adapters.bulletin_live import BulletinFetcher, BulletinIndexSearch, ClaudeWebSearch
from app.agents.base import Agent, Catalog, PlanContext
from app.core.config import settings
from app.domain import RequirementData
from app.ingest.bulletin import parse_program_page
from app.ingest.school import LAYER_TYPES, build_layers, load_spec



def effective_program_ids(program_ids: list[str], programs: dict[str, dict]) -> list[str]:
    """The student's programs plus the school/university layers that apply to them."""
    out = list(dict.fromkeys(program_ids))
    for pid in program_ids:
        out += [lid for lid in programs.get(pid, {}).get("layers") or [] if lid not in out]
    return out


def _sig(r) -> str:
    get = (lambda k: r.get(k)) if isinstance(r, dict) else (lambda k: getattr(r, k))
    return json.dumps([get("name"), get("kind"), float(get("needed") or 0), get("options") or [], get("patterns") or []], sort_keys=True)


def _requirement(d: dict, prog: dict, min_grade: str | None) -> RequirementData:
    return RequirementData(id=d["id"], program_id=prog["id"], program_name=prog["name"], program_type=prog["type"],
                           group=d.get("group", ""), name=d["name"], kind=d["kind"], needed=d["needed"], options=d.get("options", []),
                           patterns=d.get("patterns", []), notes=d.get("notes", []), catalog_year=prog.get("catalog_year"),
                           verification_status=d.get("verification_status", "parsed"), source_url=prog.get("source_url"),
                           min_grade=min_grade, evidence=d.get("evidence"))


def apply_research(catalog: Catalog, research: dict) -> None:
    """Replace catalog rules with the ones the research agent read from the live bulletin."""
    replaced = research.get("rules") or {}
    if not replaced:
        return
    programs = {**catalog.programs, **{p["id"]: p for p in research.get("layer_programs", [])}}
    min_grades = research.get("min_grades", {})
    keep = [r for r in catalog.requirements if r.program_id not in replaced]
    for pid, rules in replaced.items():
        prog = programs[pid]
        keep += [_requirement(d, prog, min_grades.get(pid, (prog.get("min_grade") or {}).get("grade"))) for d in rules]
    catalog.requirements = keep


class RequirementsResearchAgent(Agent):
    key = "requirements_research"
    title = "Requirements Research Agent"
    responsibility = ("Searches Temple's Academic Bulletin for each program and its school, fetches the official pages, "
                      "and checks the planner's rules against what the pages say today.")

    def run(self, ctx: PlanContext) -> dict:
        cat = ctx.catalog
        fetcher = BulletinFetcher()
        titles = {p["source_url"]: p["name"] for p in cat.programs.values() if p.get("source_url")}
        searchers = ([ClaudeWebSearch()] if settings.llm_enabled else []) + [BulletinIndexSearch(fetcher, titles)]
        by_program = Counter(r.program_id for r in cat.requirements)
        rules: dict[str, list[dict]] = {}
        programs_out = []
        selected = [cat.programs[p] for p in ctx.student.program_ids if p in cat.programs]
        ctx.log(f"Researching {len(selected)} program(s): " + ", ".join(p["name"] for p in selected),
                live=fetcher.live, ttl_hours=settings.bulletin_cache_ttl_hours)

        for prog in selected:
            query = f"{prog['name']} requirements Temple University"
            search, hits = None, []
            if prog["type"] != "gened":
                for s in searchers:
                    search = s.search(query, prog["type"])
                    hits = search.hits
                    ctx.log(f'Searched "{query}" via {search.provider}', results=[f"{h.title} — {h.url}" for h in hits[:3]],
                            **({"error": search.error} if search.error else {}))
                    if hits:
                        break
            official = prog.get("source_url")
            chosen = next((h.url for h in hits if h.url.rstrip("/") == (official or "").rstrip("/")), None)
            if hits and not chosen:
                ctx.log(f"Top search result for {prog['name']} is not the page the catalog was built from; using the catalog's page.",
                        top=hits[0].url, catalog=official)
            page = fetcher.get(chosen or official) if official else None
            entry = {"program_id": prog["id"], "name": prog["name"], "type": prog["type"], "query": query if search else None,
                     "search_provider": search.provider if search else None,
                     "search_results": [{"title": h.title, "url": h.url, "score": h.score} for h in hits[:3]],
                     "search_matched_catalog_page": bool(chosen), "url": official,
                     "fetch": {"mode": page.mode, "retrieved_at": page.retrieved_at, "status": page.status, "error": page.error, "sha": page.sha}
                     if page else None, "changes": None}
            if page and page.text and prog["type"] != "gened":
                parsed = parse_program_page(page.text, official)
                fresh = parsed["requirements"]
                for j, r in enumerate(fresh, 1):
                    r["id"] = f"{prog['id']}-r{j}"
                old = [r for r in cat.requirements if r.program_id == prog["id"]]
                old_sigs, new_sigs = Counter(map(_sig, old)), Counter(map(_sig, fresh))
                added, removed = sum((new_sigs - old_sigs).values()), sum((old_sigs - new_sigs).values())
                entry["changes"] = {"added": added, "removed": removed, "rules_on_page": len(fresh),
                                    "catalog_year_on_page": parsed["catalog_year"]}
                ctx.cite("bulletin", f"{prog['name']} — Academic Bulletin ({page.mode})", official, page.retrieved_at,
                         "fetched_live" if page.mode in ("live", "cache") else "snapshot")
                if added or removed:
                    rules[prog["id"]] = fresh
                    ctx.log(f"{prog['name']}: the bulletin page differs from the ingested rules (+{added} / -{removed}); "
                            "using the rules on the page.", mode=page.mode)
                else:
                    ctx.log(f"{prog['name']}: {len(fresh)} rules on the page match the ingested rules ({page.mode}).")
            elif prog["type"] != "gened":
                ctx.log(f"{prog['name']}: bulletin page unavailable ({page.error if page else 'no URL'}); using ingested rules "
                        f"({by_program.get(prog['id'], 0)} rules).")
            programs_out.append(entry)

        # School / college and university layers, re-built from the live school pages.
        built = build_layers(load_spec(settings.data_dir), [p for p in selected if p["type"] not in LAYER_TYPES and p["type"] != "gened"],
                             cat.courses, fetcher.text)
        layers_out = []
        for layer in built["layers"]:
            old = [r for r in cat.requirements if r.program_id == layer["id"]]
            if Counter(map(_sig, old)) != Counter(map(_sig, layer["requirements"])) or not old:
                rules[layer["id"]] = layer["requirements"]
            checks = [c for c in built["checks"] if c["layer"] == layer["id"]]
            missing = [c["rule"] for c in checks if not c["found"]]
            fetched = next((f for f in reversed(fetcher.results) if f.url == layer["source_url"].split("#")[0]), None)
            layers_out.append({"id": layer["id"], "name": layer["name"], "type": layer["type"], "url": layer["source_url"],
                               "rules": len(layer["requirements"]), "evidence_checked": len(checks), "evidence_missing": missing,
                               "fetch_mode": fetched.mode if fetched else None,
                               "retrieved_at": fetched.retrieved_at if fetched else None})
            ctx.cite("bulletin_school", layer["name"], layer["source_url"], fetched.retrieved_at if fetched else None,
                     "fetched_live" if fetched and fetched.mode in ("live", "cache") else "snapshot")
            ctx.log(f"{layer['name']}: {len(layer['requirements'])} rule(s); {len(checks) - len(missing)}/{len(checks)} "
                    "bulletin quotes found on the page" + (f"; changed: {', '.join(missing)}" if missing else ""))
        effective = list(dict.fromkeys([p["id"] for p in selected] + [lid for links in built["links"].values() for lid in links]))
        out = {
            "programs": programs_out, "school_layers": layers_out, "effective_programs": effective,
            "layer_programs": [{k: v for k, v in layer.items() if k != "requirements"} for layer in built["layers"]],
            "min_grades": {pid: mg["grade"] for pid, mg in built["min_grades"].items()},
            "min_grade_sources": built["min_grades"],
            "rules": rules,
            "fetches": [{"url": f.url, "mode": f.mode, "retrieved_at": f.retrieved_at, "error": f.error} for f in fetcher.results],
            "live_enabled": fetcher.live,
        }
        apply_research(cat, out)
        for lp in out["layer_programs"]:
            cat.programs.setdefault(lp["id"], {**lp, "supported": True})
        return out

    def summarize(self, o: dict) -> str:
        modes = Counter(f["mode"] for f in o["fetches"] if "sitemap" not in f["url"] and "robots" not in f["url"])
        changed = sum(1 for p in o["programs"] if (p.get("changes") or {}).get("added") or (p.get("changes") or {}).get("removed"))
        return (f"Checked {len(o['programs'])} program page(s) and {len(o['school_layers'])} school/university layer(s) "
                f"({', '.join(f'{v} {k}' for k, v in modes.items())}); {changed} program(s) changed since ingest.")

    def decision(self, ctx, o):
        missing = [f"{l['name']}: source text changed for {', '.join(l['evidence_missing'])}" for l in o["school_layers"] if l["evidence_missing"]]
        offline = [f"{p['name']}: page {p['fetch']['mode']}" + (f" ({p['fetch']['error']})" if p["fetch"].get("error") else "")
                   for p in o["programs"] if p.get("fetch") and p["fetch"]["mode"] in ("snapshot", "unavailable")]
        not_found = [f"Search did not return the catalog page for {p['name']}" for p in o["programs"]
                     if p["query"] and not p["search_matched_catalog_page"]]
        return {"task": "Find and read the official bulletin pages for each program and its school; check the planner's rules against them",
                "data_sources": sorted({p["search_provider"] for p in o["programs"] if p["search_provider"]})
                + [f"{l['name']} ({l['fetch_mode'] or 'n/a'})" for l in o["school_layers"]],
                "findings": [self.summarize(o)] + [f"{l['name']}: {l['rules']} rule(s), {l['evidence_checked'] - len(l['evidence_missing'])}/"
                                                   f"{l['evidence_checked']} quotes verified on the page" for l in o["school_layers"]],
                "recommendation": "Apply the program, school and university requirements together; rules whose source text changed need advisor review.",
                "validation": {"status": "warnings" if missing or offline or not_found else "passed",
                               "detail": "All quotes found on the current pages" if not missing else f"{len(missing)} layer(s) with changed text"},
                "unresolved": (missing + offline + not_found)[:8]}
