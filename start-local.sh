#!/usr/bin/env bash
set -euo pipefail

docker compose up -d postgres redis
backend_python="${BACKEND_PYTHON:-backend/.venv/bin/python}"
"$backend_python" -m alembic -c backend/alembic.ini upgrade head

"$backend_python" -m uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000 &
backend_pid=$!
(cd frontend && npm run dev) &
frontend_pid=$!

trap 'kill "$backend_pid" "$frontend_pid"' EXIT INT TERM
echo "ByteLink is starting. Open http://localhost:5173"
wait
