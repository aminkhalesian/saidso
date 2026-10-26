#!/usr/bin/env bash
# One-command start on macOS/Linux: sets up Python + frontend on first run, seeds data, serves on :8000
set -e
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r backend/requirements.txt
if [ ! -d frontend/dist ]; then (cd frontend && npm install --no-audit --no-fund && npm run build); fi
cd backend
if [ ! -f engine.db ]; then
  if [ -f ../demo/engine.demo.db ]; then cp ../demo/engine.demo.db engine.db; echo "Loaded the demo database from demo/engine.demo.db"
  else python -m app.cli seed; fi
fi
echo "Open http://localhost:8000"
uvicorn app.main:app --port 8000
