@echo off
setlocal

docker compose up -d postgres redis
if errorlevel 1 exit /b 1

call backend\.venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

python -m alembic -C backend\alembic.ini upgrade head
if errorlevel 1 exit /b 1

start "ByteLink backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
start "ByteLink frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo ByteLink is starting. Open http://localhost:5173
