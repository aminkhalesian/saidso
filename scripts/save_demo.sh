#!/usr/bin/env bash
# Save today's demo state into the repo so anyone who clones it sees the same data:
#   demo/engine.demo.db        the database (start.sh loads it when there is no backend/engine.db)
#   demo/saidso-offline.html   one-file copy of the whole app
# Run from the repo root, with the .venv active:  ./scripts/save_demo.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p demo
cp backend/engine.db demo/engine.demo.db
python scripts/export_static.py
cp demo/saidso-offline.html docs/index.html      # GitHub Pages serves docs/index.html
echo "Saved. Now: git add demo docs && git commit -m 'Demo data' && git push"
