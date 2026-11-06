import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
# TEST_DATABASE_URL runs the suite against another server (e.g. MySQL); it must be a throwaway database.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["ANTHROPIC_API_KEY"] = ""  # tests must be deterministic and offline
os.environ["LIVE_BULLETIN_RESEARCH"] = "false"
# Most workflow tests exercise requirement-driven planning; test_grad_plan.py turns the gate back on.
os.environ["REQUIRE_GRAD_PLAN"] = "false"
os.environ["DATA_DIR"] = str(Path(__file__).resolve().parent / "fixtures" / "catalog")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
