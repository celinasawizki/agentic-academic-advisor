"""Run the full agent pipeline once for every program in data/temple (each with GenEd)
and report failures plus requirement coverage per program type and school.

    python -m scripts.sweep_programs [--workers 8] [--limit N] [--live]

Uses a throwaway SQLite database per worker. Without --live the Requirements
Research Agent reads the pages cached by the ingest crawl (no requests to Temple)."""

import json
import os
import sys
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data" / "temple"
STUDENT = {"name": "Sweep", "academic_year": "Sophomore", "expected_graduation": "2029-05", "planning_term": "202703",
           "credit_target": 15, "credit_min": 12, "credit_max": 18, "consent_to_process": True, "interests_text": "",
           "transcript": [{"course": "ENG 0802", "status": "completed", "grade": "B"}], "availability": []}


def _worker(args: tuple[list[str], bool]) -> list[dict]:
    program_ids, live = args
    tmp = tempfile.mkdtemp()
    os.environ.update(DATABASE_URL=f"sqlite:///{tmp}/sweep.db", ANTHROPIC_API_KEY="", LIVE_BULLETIN_RESEARCH=str(live).lower(),
                      REQUIRE_GRAD_PLAN="false")  # exercises requirement-driven planning
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import logging
    logging.disable(logging.WARNING)
    from fastapi.testclient import TestClient

    from app.main import app
    out = []
    with TestClient(app) as c:
        for pid in program_ids:
            t = time.time()
            row = {"program": pid}
            try:
                r = c.post("/api/students", json={**STUDENT, "programs": [pid] if pid == "gened" else [pid, "gened"]})
                r.raise_for_status()
                auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
                plan_id = c.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth).json()["plan_id"]
                plan = c.get(f"/api/plans/{plan_id}", headers=auth).json()
                st = plan["state"]
                row["status"] = plan["status"]
                row["error"] = (st.get("_error") or "").strip().splitlines()[-1:] if plan["status"] != "complete" else None
                if plan["status"] == "complete":
                    reqs = st["degree_requirements"]["requirements"]
                    own = [q for q in reqs if q["program_id"] == pid]
                    row.update(
                        rules=len(own), layers=[x["id"] for x in st["degree_requirements"].get("layers", [])],
                        layer_rules=sum(1 for q in reqs if q["program_type"] in ("school", "university")),
                        open_rules=len(st["degree_requirements"]["remaining"]),
                        options=len(st["schedule_optimization"]["options"]),
                        credits=[o["credits"] for o in st["schedule_optimization"]["options"]],
                        min_grade=next((q["min_grade"] for q in own if q.get("min_grade")), None),
                        research_modes=sorted({f["mode"] for f in st["requirements_research"]["fetches"]}),
                    )
            except Exception as e:  # noqa: BLE001 - the sweep reports every failure
                row.update(status="exception", error=[f"{type(e).__name__}: {e}"])
            row["seconds"] = round(time.time() - t, 1)
            out.append(row)
    return out


def main() -> None:
    args = sys.argv[1:]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 8
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    progs = [p for p in json.loads((DATA / "programs.json").read_text())["programs"] if p["type"] not in ("school", "university")]
    meta = {p["id"]: p for p in progs}
    ids = [p["id"] for p in progs][:limit]
    chunks = [(ids[i::workers], "--live" in args) for i in range(workers)]
    t = time.time()
    with ProcessPoolExecutor(workers) as ex:
        rows = [r for chunk in ex.map(_worker, chunks) for r in chunk]
    failed = [r for r in rows if r["status"] != "complete"]
    by_type: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        p = meta[r["program"]]
        by_type[p["type"]]["programs"] += 1
        by_type[p["type"]]["complete"] += r["status"] == "complete"
        by_type[p["type"]]["with_school_layer"] += bool(r.get("layers"))
        by_type[p["type"]]["with_schedule"] += bool(r.get("options"))
        by_type[p["type"]]["with_min_grade"] += bool(r.get("min_grade"))
    print(f"{len(rows)} programs in {time.time() - t:.0f}s; {len(failed)} failed")
    for k, v in by_type.items():
        print(f"  {k:12} " + ", ".join(f"{a}={b}" for a, b in v.items()))
    majors_without_layer = [r["program"] for r in rows if meta[r["program"]]["type"] == "major" and not r.get("layers")]
    no_schedule = [r["program"] for r in rows if r["status"] == "complete" and not r.get("options")]
    print("majors without a school layer:", majors_without_layer or "none")
    print("programs without any schedule option:", no_schedule or "none")
    for r in failed:
        print("  FAILED", r["program"], r["status"], r.get("error"))
    report = DATA.parent.parent / "docs" / "audit" / "program-sweep.json"
    report.write_text(json.dumps({"generated_s": round(time.time() - t), "summary": {k: dict(v) for k, v in by_type.items()},
                                  "failed": failed, "rows": rows}, indent=1))
    print(f"Wrote {report}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
