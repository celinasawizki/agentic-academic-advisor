import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ANTHROPIC_API_KEY"] = ""  # tests must be deterministic and offline
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
