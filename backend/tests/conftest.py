"""Every test run uses its own temporary database. The demo database (backend/engine.db) is never opened or changed."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="saidso-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}"
os.environ.setdefault("MOCK_LLM", "1")     # no network, no key needed; the live test opts in (tests/test_live_llm.py)


def pytest_sessionfinish(session, exitstatus):
    _TMP.unlink(missing_ok=True)
