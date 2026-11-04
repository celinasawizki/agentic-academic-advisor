# Testing & Verification
| Check | Command | Notes |
|---|---|---|
| Unit + workflow | `python -m pytest tests -q` | Workflow tests use `tests/fixtures/catalog` (synthetic) |
| School layers | `python -m pytest tests/test_school_layers.py -q` | |
| Frontend | `npx tsc --noEmit && npm run lint && npm run build` | in `apps/web` |
| Program sweep | `python -m scripts.sweep_programs` | → `docs/audit/program-sweep.json` |
| Stress | `python -m scripts.stress_plans --n 120 --workers 8 --seed 7` | → `docs/audit/stress-report.json`; exit 1 on invariant violation |

Audit baseline: 71 passed (see `AUDIT_REPORT.md`). Every fixed bug gets a test.
