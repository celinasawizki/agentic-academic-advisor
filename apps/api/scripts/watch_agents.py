"""Live terminal feed of the agent orchestration: every AgentExecution the
orchestrator persists (start, finish, duration, summary, research log lines and
the sources each agent cited), plus plan status changes.

    python -m scripts.watch_agents            (from apps/api; reads the same database as the API)

Read-only: it only queries the database."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal  # noqa: E402
from app.models import AgentExecution, PlanRun  # noqa: E402

DIM, BOLD, RED, GREEN, YELLOW, CYAN, MAGENTA, RESET = (f"\033[{c}m" for c in (2, 1, 31, 32, 33, 36, 35, 0))
STATUS = {"running": f"{CYAN}▶ started{RESET}", "complete": f"{GREEN}✓ complete{RESET}", "failed": f"{RED}✗ failed{RESET}",
          "skipped": f"{DIM}↺ reused{RESET}", "pending": f"{DIM}… queued{RESET}"}


def stamp() -> str:
    return time.strftime("%H:%M:%S")


def out(plan: str, it: int | None, text: str) -> None:
    head = f"{DIM}{stamp()}{RESET}  {MAGENTA}{plan[-6:]}{RESET} {DIM}run {it}{RESET}" if it else f"{DIM}{stamp()}{RESET}  {MAGENTA}{plan[-6:]}{RESET}      "
    print(f"{head}  {text}", flush=True)


def main() -> None:
    print(f"{BOLD}Agent orchestration feed{RESET} {DIM}(polling the planner database every second; Ctrl-C to stop){RESET}\n", flush=True)
    seen: dict[int, tuple[str, int, int]] = {}
    plans: dict[str, str] = {}
    db = SessionLocal()
    first = True
    while True:
        try:
            db.expire_all()
            for p in db.query(PlanRun).order_by(PlanRun.created_at.desc()).limit(20).all():
                if plans.get(p.id) != p.status:
                    if not first or p.status == "running":
                        tone = {"running": CYAN, "complete": GREEN, "failed": RED}.get(p.status, DIM)
                        out(p.id, None, f"{BOLD}plan {tone}{p.status}{RESET}  {DIM}student {p.student_id}{RESET}")
                    plans[p.id] = p.status
            rows = (db.query(AgentExecution).order_by(AgentExecution.id.desc()).limit(200).all())[::-1]
            for ex in rows:
                prev = seen.get(ex.id)
                state = (ex.status, len(ex.log or []), len(ex.sources or []))
                if prev == state:
                    continue
                seen[ex.id] = state
                if first and ex.status in ("complete", "failed", "skipped"):
                    continue  # don't replay history on start-up
                title = f"{BOLD}{_title(ex.agent)}{RESET}"
                if prev is None or prev[0] != ex.status:
                    extra = ""
                    if ex.status in ("complete", "failed") and ex.started_at and ex.finished_at:
                        extra = f" {DIM}{(ex.finished_at - ex.started_at).total_seconds():.1f}s · {ex.mode}{RESET}"
                    if ex.status != "pending":
                        out(ex.plan_id, ex.iteration, f"{STATUS.get(ex.status, ex.status)}  {title}{extra}")
                for line in (ex.log or [])[(prev[1] if prev else 0):]:
                    out(ex.plan_id, ex.iteration, f"    {DIM}·{RESET} {line['message'][:160]}")
                for src in (ex.sources or [])[(prev[2] if prev else 0):]:
                    if src.get("url"):
                        out(ex.plan_id, ex.iteration, f"    {YELLOW}↗{RESET} {src['description'][:70]} {DIM}{src['url']}{RESET}")
                if ex.status == "complete" and ex.summary:
                    out(ex.plan_id, ex.iteration, f"    {GREEN}→{RESET} {ex.summary[:170]}")
                if ex.status == "failed" and ex.error:
                    out(ex.plan_id, ex.iteration, f"    {RED}{ex.error[:170]}{RESET}")
            first = False
        except KeyboardInterrupt:
            return
        except Exception as e:  # noqa: BLE001 - keep watching through transient sqlite locks
            print(f"{DIM}{stamp()}  (db busy: {type(e).__name__}){RESET}", flush=True)
            db.close()
            db = SessionLocal()
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            return


TITLES: dict[str, str] = {}


def _title(key: str) -> str:
    if not TITLES:
        from app.orchestrator import PIPELINE
        TITLES.update({a.key: a.title for a in PIPELINE})
    return TITLES.get(key, key)


if __name__ == "__main__":
    main()
