"""Randomized end-to-end check: realistic students (major + optional minor/certificate,
partial transcripts with some failing grades, jobs, F-1) through the whole pipeline and
every follow-up endpoint, asserting invariants on everything the agents return.

    python -m scripts.stress_plans [--n 120] [--workers 8] [--seed 7]

Exit code 1 if any invariant is violated; details in docs/audit/stress-report.json."""

import json
import os
import random
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data" / "temple"
DAYS = ["M", "T", "W", "R", "F"]
GRADES = ["A", "A", "A-", "B+", "B", "B", "B-", "C+", "C", "C-", "D", "F", "W"]


def mins(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def make_student(rng: random.Random, programs: dict, courses: dict) -> dict:
    majors = [p for p in programs.values() if p["type"] == "major"]
    minors = [p for p in programs.values() if p["type"] == "minor"]
    certs = [p for p in programs.values() if p["type"] == "certificate"]
    chosen = [rng.choice(majors)]
    if rng.random() < 0.5:
        chosen.append(rng.choice(minors))
    if rng.random() < 0.3:
        chosen.append(rng.choice(certs))
    pool = [c for p in chosen for r in p["requirements"] for o in r.get("options", []) for c in o if c in courses]
    pool += ["ENG 0802", "IH 0851", "IH 0852", "MATH 1041", "SPAN 1001", "SPAN 1002", "PSY 1001"]
    transcript, seen = [], set()
    for c in rng.sample(pool, min(len(pool), rng.randint(0, 16))):
        if c in seen:
            continue
        seen.add(c)
        status = rng.choices(["completed", "in_progress", "transfer"], [7, 2, 1])[0]
        transcript.append({"course": c, "status": status,
                           "grade": None if status == "in_progress" else ("TR" if status == "transfer" else rng.choice(GRADES))})
    avail = []
    if rng.random() < 0.6:
        d = rng.sample(DAYS, rng.randint(1, 3))
        start = rng.choice(["08:00", "09:00", "12:00", "13:00", "16:00"])
        end = f"{min(21, int(start[:2]) + rng.randint(3, 6)):02d}:00"
        avail += [{"day": x, "start": start, "end": end, "kind": "hard", "label": "Job"} for x in d]
    if rng.random() < 0.4:
        avail.append({"day": "F", "start": "07:00", "end": "22:00", "kind": "soft", "label": "Prefer Fridays off"})
    target = rng.choice([12, 15, 15, 16, 18])
    return {"name": "Stress", "academic_year": rng.choice(["Freshman", "Sophomore", "Junior", "Senior"]),
            "expected_graduation": rng.choice(["2027-05", "2028-05", "2029-05"]), "planning_term": "202703",
            "programs": [p["id"] for p in chosen] + ["gened"], "credit_target": target, "credit_min": 12, "credit_max": 18,
            "consent_to_process": True, "interests_text": rng.choice(["", "data science and machine learning", "health policy",
                                                                    "music and film", "law, ethics and justice"]),
            "transcript": transcript, "availability": avail, "f1_status": rng.choice(["no", "no", "yes"])}


def check_plan(plan: dict, student: dict, courses: dict) -> list[str]:
    errs = []
    st = plan["state"]
    if plan["status"] != "complete":
        return [f"plan {plan['status']}: {(st.get('_error') or '').strip().splitlines()[-1:]}"]
    done_agents = {a["agent"] for a in plan["agents"] if a["status"] == "complete"}
    if len(done_agents) < 10:
        errs.append(f"only {len(done_agents)} agents completed")
    for a in plan["agents"]:
        if a["status"] == "complete" and not (a.get("decision") or {}).get("task"):
            errs.append(f"{a['agent']}: no decision record")
    passed = {t["course"] for t in student["transcript"] if t["status"] in ("completed", "transfer") and t["grade"] not in ("F", "W")}
    in_prog = {t["course"] for t in student["transcript"] if t["status"] == "in_progress"}
    hard = [b for b in st["_student"]["availability"] if b["kind"] == "hard"]
    reqs = {r["id"]: r for r in st["degree_requirements"]["requirements"]}
    expl = {o["option_id"]: {c["course"]: c for c in o["courses"]} for o in st["student_explanation"].get("options", [])}
    disc = st["course_discovery"]["courses"]
    for o in st["schedule_optimization"]["options"]:
        secs = o["sections"]
        tag = o["strategy"]
        explained = expl.get(o["id"], {})
        prim = [s for s in secs if s.get("component", "primary") == "primary"]
        credits = sum(s["credits"] for s in prim)
        if abs(credits - o["credits"]) > 0.01:
            errs.append(f"{tag}: credits {o['credits']} != sum {credits}")
        prefs = st["_student"]["preferences"]
        if not prefs["credit_min"] - 0.01 <= o["credits"] <= prefs["credit_max"] + 0.01:
            errs.append(f"{tag}: credits {o['credits']} outside {prefs['credit_min']}-{prefs['credit_max']}")
        for i, a in enumerate(secs):
            for b in secs[i + 1:]:
                for ma in a["meetings"]:
                    for mb in b["meetings"]:
                        if set(ma["days"]) & set(mb["days"]) and mins(ma["start"]) < mins(mb["end"]) and mins(mb["start"]) < mins(ma["end"]):
                            errs.append(f"{tag}: time conflict {a['id']} / {b['id']}")
            for m in a["meetings"]:
                for blk in hard:
                    if blk["day"] in m["days"] and mins(m["start"]) < mins(blk["end"]) and mins(blk["start"]) < mins(m["end"]):
                        errs.append(f"{tag}: {a['id']} overlaps hard block {blk['label']} {blk['day']}")
        codes = {s["course"] for s in secs}
        for c in codes:
            if c in passed or c in in_prog:
                errs.append(f"{tag}: schedules already taken {c}")
            if disc.get(c, {}).get("prereq_status") == "missing":
                errs.append(f"{tag}: {c} has missing prerequisites")
            course = courses.get(c)
            if course:
                for g in course.get("prereqs", []):
                    unmet = not any(x in passed for x in g)
                    if unmet and any(x in codes and x != c for x in g) and "concurrent" not in course.get("prereq_text", "").lower():
                        errs.append(f"{tag}: {c} scheduled with its own prerequisite {[x for x in g if x in codes]}")
            if c not in explained:
                errs.append(f"{tag}: {c} has no explanation")
            elif not explained[c].get("reasons"):
                errs.append(f"{tag}: {c} explanation has no reasons")
        for s in secs:
            for rid in s.get("requirement_ids", []):
                if rid not in reqs and rid != "FREE_ELECTIVE":
                    errs.append(f"{tag}: unknown requirement id {rid}")
        comps: dict[str, set] = {}
        for s in secs:
            comps.setdefault(s["course"], set()).add(s.get("component", "primary"))
        for c, have in comps.items():
            if "primary" not in have:
                errs.append(f"{tag}: {c} has a lab/recitation without its primary section")
        if student["f1_status"] == "yes":
            f1 = o.get("f1") or {}
            if f1.get("status") == "below":
                errs.append(f"{tag}: F-1 below full time")
    rc = st["degree_requirements"].get("reliability_counts", {})
    real = sum(1 for r in reqs.values() if r["kind"] not in ("note", "policy"))
    if sum(rc.values()) != real:
        errs.append(f"reliability counts {sum(rc.values())} != rules {real}")
    for r in reqs.values():
        if r["status"] == "complete" and r["kind"] in ("count", "credits") and r["remaining_needed"] > 0:
            errs.append(f"{r['id']}: complete with remaining {r['remaining_needed']}")
        for c in r["completed"]:
            if c not in passed:
                errs.append(f"{r['id']}: counts {c} which is not passed")
    if not st["schedule_optimization"]["options"] and not st["schedule_optimization"].get("infeasible_strategies"):
        errs.append("no options and no infeasibility explanation")
    return errs


def _worker(args):
    seed, n, worker = args
    tmp = tempfile.mkdtemp()
    os.environ.update(DATABASE_URL=f"sqlite:///{tmp}/stress.db", ANTHROPIC_API_KEY="", LIVE_BULLETIN_RESEARCH="false")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import logging
    logging.disable(logging.WARNING)
    from fastapi.testclient import TestClient

    from app.main import app
    programs = {p["id"]: p for p in json.loads((DATA / "programs.json").read_text())["programs"]
                if p["type"] in ("major", "minor", "certificate")}
    courses = {c["code"]: c for c in json.loads((DATA / "courses.json").read_text())["courses"]}
    rng = random.Random(seed * 1000 + worker)
    rows = []
    with TestClient(app, raise_server_exceptions=False) as c:
        for _ in range(n):
            s = make_student(rng, programs, courses)
            row = {"programs": s["programs"], "errors": []}
            t = time.time()
            try:
                r = c.post("/api/students", json=s)
                if r.status_code != 200:
                    row["errors"].append(f"create student {r.status_code}: {r.text[:200]}")
                    rows.append(row)
                    continue
                auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
                pid = c.post("/api/plans", json={"student_id": r.json()["id"]}, headers=auth).json()["plan_id"]
                plan = c.get(f"/api/plans/{pid}", headers=auth).json()
                row["errors"] += check_plan(plan, s, courses)
                if plan["status"] == "complete":
                    opts = plan["state"]["schedule_optimization"]["options"]
                    if opts:  # manual validation of an agent-built option must agree with the Review Agent
                        v = c.post(f"/api/plans/{pid}/validate", json={"section_ids": [x["id"] for x in opts[0]["sections"]]}, headers=auth)
                        if v.status_code != 200:
                            row["errors"].append(f"validate {v.status_code}: {v.text[:150]}")
                        elif not v.json().get("valid", True):
                            failed = [x for x in v.json().get("checks", []) if not x.get("passed") and x.get("severity") == "error"]
                            row["errors"].append(f"validate rejects agent option: {[x.get('check') for x in failed][:4]}")
                    msg = rng.choice(["I got a job on Tuesdays and Thursdays from 9 to 5", "Give me Fridays off",
                                      "I want to take 12 credits", "No classes before 10am"])
                    m = c.post(f"/api/plans/{pid}/modify", json={"message": msg}, headers=auth)
                    if m.status_code != 200:
                        row["errors"].append(f"modify {m.status_code}: {m.text[:150]}")
                    else:
                        p2 = c.get(f"/api/plans/{pid}", headers=auth).json()
                        s2 = {**s, "availability": p2["state"]["_student"]["availability"]}
                        row["errors"] += [f"after '{msg}': {e}" for e in check_plan(p2, s2, courses)]
                        if p2["status"] == "complete":
                            g = c.post(f"/api/plans/{pid}/regenerate", headers=auth)
                            if g.status_code != 200:
                                row["errors"].append(f"regenerate {g.status_code}")
                            else:
                                p3 = c.get(f"/api/plans/{pid}", headers=auth).json()
                                row["errors"] += [f"after regenerate: {e}" for e in check_plan(p3, s2, courses)]
            except Exception as e:  # noqa: BLE001
                row["errors"].append(f"exception {type(e).__name__}: {e}")
            row["seconds"] = round(time.time() - t, 1)
            rows.append(row)
    return rows


def main():
    a = sys.argv[1:]
    n = int(a[a.index("--n") + 1]) if "--n" in a else 120
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else 8
    seed = int(a[a.index("--seed") + 1]) if "--seed" in a else 7
    per = [n // workers + (1 if i < n % workers else 0) for i in range(workers)]
    t = time.time()
    with ProcessPoolExecutor(workers) as ex:
        rows = [r for chunk in ex.map(_worker, [(seed, k, i) for i, k in enumerate(per)]) for r in chunk]
    bad = [r for r in rows if r["errors"]]
    from collections import Counter
    kinds = Counter(e.split(":")[0] if not e.startswith("after") else e.split(":")[1].strip() for r in bad for e in r["errors"])
    print(f"{len(rows)} students in {time.time() - t:.0f}s; {len(bad)} with invariant violations")
    for k, v in kinds.most_common(30):
        print(f"  {v:4}  {k}")
    for r in bad[:25]:
        print("  ", r["programs"], r["errors"][:3])
    out = DATA.parent.parent / "docs" / "audit" / "stress-report.json"
    out.write_text(json.dumps({"seed": seed, "students": len(rows), "violations": len(bad), "rows": rows}, indent=1))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
