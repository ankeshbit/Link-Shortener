@echo off
setlocal

echo [1/4] Starting PostgreSQL and Redis containers...
docker compose up -d postgres redis
if errorlevel 1 (
    echo Note: Docker compose returned non-zero. Ensure Docker Desktop is running, or running services natively.
)

echo [2/4] Activating backend virtual environment...
if exist backend\.venv\Scripts\activate.bat (
    call backend\.venv\Scripts\activate.bat
)

echo [3/4] Running database migrations...
python -m alembic -c backend\alembic.ini upgrade head
if errorlevel 1 (
    echo Migration failed. Please ensure PostgreSQL is reachable.
    pause
    exit /b 1
)

echo [4/4] Launching FastAPI backend and Vite frontend...
start "ByteLink Backend (FastAPI)" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
start "ByteLink Frontend (Vite)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo =======================================================
echo ByteLink local development environment is running!
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000
echo Docs:     http://localhost:8000/docs
echo =======================================================
