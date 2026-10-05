#!/usr/bin/env bash
# Start backend (:8000) and frontend (:5173) together. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
(cd "$ROOT/backend" && uv run uvicorn app.main:app --reload --port 8000) &
BACK=$!
(cd "$ROOT/frontend" && npm run dev -- --port 5173) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' INT TERM EXIT
echo "Backend http://localhost:8000/docs  |  App http://localhost:5173"
wait
