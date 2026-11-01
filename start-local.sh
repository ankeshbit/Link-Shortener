#!/usr/bin/env bash
set -euo pipefail

echo "[1/4] Starting PostgreSQL and Redis via Docker Compose..."
if command -v docker &> /dev/null; then
    docker compose up -d postgres redis || true
else
    echo "Docker not found in PATH; ensuring native services are running."
fi

backend_python="${BACKEND_PYTHON:-backend/.venv/bin/python}"
if [ ! -f "$backend_python" ]; then
    backend_python="python3"
fi

echo "[2/4] Running database migrations..."
(cd backend && "$backend_python" -m alembic -c alembic.ini upgrade head)

echo "[3/4] Starting FastAPI backend on http://127.0.0.1:8000..."
(cd backend && "$backend_python" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000) &
backend_pid=$!

echo "[4/4] Starting Vite frontend on http://localhost:5173..."
(cd frontend && npm run dev) &
frontend_pid=$!

cleanup() {
    echo ""
    echo "Shutting down ByteLink services..."
    kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
    pkill -P "$backend_pid" 2>/dev/null || true
    pkill -P "$frontend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
    wait "$frontend_pid" 2>/dev/null || true
    echo "All local services stopped cleanly."
}
trap cleanup EXIT INT TERM

echo "======================================================="
echo "ByteLink is running locally:"
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "======================================================="
wait
