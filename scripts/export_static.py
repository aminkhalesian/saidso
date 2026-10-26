"""Make one HTML file of the whole app, with today's data inside. No server needed to open it.

Run from the repo root with the same environment as the app (your .venv):
    python scripts/export_static.py
Result: frontend/dist-static/index.html (also copied to demo/saidso-offline.html)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

http = TestClient(app)
snap: dict = {}


def grab(path: str):
    r = http.get("/api" + path)
    r.raise_for_status()
    snap[path] = r.json()
    return snap[path]


grab("/health")
for c in grab("/clients"):
    cid = c["id"]
    over = grab(f"/clients/{cid}/overview?window=90")
    for row in over["renewals"]:
        grab(f"/clients/{cid}/accounts/{row['account_id']}")
    for w in (30, 60, 90):
        grab(f"/clients/{cid}/retention?window={w}")
    for part in ("portfolio", "sources", "trust", "sample-transcript"):
        grab(f"/clients/{cid}/{part}")
snap = {(k if "/retention" in k else k.split("?")[0]): v for k, v in snap.items()}

(ROOT / "frontend" / "static-snapshot.json").write_text(json.dumps(snap))
subprocess.run(["npm", "run", "build:static"], cwd=ROOT / "frontend", check=True)
(ROOT / "demo").mkdir(exist_ok=True)
out = ROOT / "demo" / "saidso-offline.html"
shutil.copy(ROOT / "frontend" / "dist-static" / "index.html", out)
print(f"\nDone: {out} ({out.stat().st_size // 1024} KB, {len(snap)} data pages)")
