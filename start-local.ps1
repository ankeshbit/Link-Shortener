# ByteLink Complete Local Development Startup Script (PowerShell)
# Enforces prerequisites, environment files, database, Redis, migrations, and servers.

$ErrorActionPreference = "Stop"

function Test-PortOpen {
    param(
        [string]$ComputerName = "127.0.0.1",
        [int]$Port,
        [int]$TimeoutMs = 1000
    )
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect($ComputerName, $Port, $null, $null)
        $wait = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if (-not $wait) {
            $tcp.Close()
            return $false
        }
        $tcp.EndConnect($iar)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host " ByteLink - Local Development Environment Setup        " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

# 1. Check Required Prerequisites (Python, Node.js, npm)
Write-Host "`n[1/7] Checking prerequisites..." -ForegroundColor Yellow

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Error "Python 3 is required but not found in PATH. Install Python 3.10+ and re-run."
    exit 1
}
$PythonVersion = & python --version 2>&1
Write-Host "  Found $PythonVersion" -ForegroundColor Green

$NodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $NodeCmd) {
    Write-Error "Node.js is required but not found in PATH. Install Node.js 18+ and re-run."
    exit 1
}
$NodeVersion = & node --version
Write-Host "  Found Node.js $NodeVersion" -ForegroundColor Green

$NpmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $NpmCmd) {
    Write-Error "npm is required but not found in PATH."
    exit 1
}

# 2. Verify Environment Files
Write-Host "`n[2/7] Verifying environment files..." -ForegroundColor Yellow
$BackendEnv = Join-Path $PSScriptRoot "backend\.env"
$FrontendEnv = Join-Path $PSScriptRoot "frontend\.env"

if (-not (Test-Path $BackendEnv)) {
    Write-Host "  Creating backend\.env from template..." -ForegroundColor Gray
    Copy-Item (Join-Path $PSScriptRoot "backend\.env.example") $BackendEnv
}
Write-Host "  backend\.env verified." -ForegroundColor Green

if (-not (Test-Path $FrontendEnv)) {
    Write-Host "  Creating frontend\.env from template..." -ForegroundColor Gray
    Copy-Item (Join-Path $PSScriptRoot "frontend\.env.example") $FrontendEnv
}
Write-Host "  frontend\.env verified." -ForegroundColor Green

# 3. Check and Start PostgreSQL and Redis
Write-Host "`n[3/7] Checking database (PostgreSQL :5432) and cache (Redis :6379)..." -ForegroundColor Yellow

$HasDocker = (Get-Command docker -ErrorAction SilentlyContinue) -ne $null
if ($HasDocker) {
    try {
        Write-Host "  Starting Docker Compose services (postgres, redis)..." -ForegroundColor Gray
        docker compose up -d postgres redis
    } catch {
        Write-Warning "  Docker compose encountered an issue. Checking for native services..."
    }
}

# If Redis is not yet running on port 6379, check if local portable redis exists
if (-not (Test-PortOpen -Port 6379)) {
    $PortableRedis = "C:\Users\ankes\.local_redis\redis-server.exe"
    if (Test-Path $PortableRedis) {
        Write-Host "  Starting local Redis service on port 6379..." -ForegroundColor Gray
        Start-Process -FilePath $PortableRedis -ArgumentList "--port 6379" -WindowStyle Hidden
        Start-Sleep -Seconds 1
    }
}

# Wait for PostgreSQL
$PostgresReady = $false
for ($i = 1; $i -le 10; $i++) {
    if (Test-PortOpen -Port 5432) {
        $PostgresReady = $true
        break
    }
    Write-Host "  Waiting for PostgreSQL on localhost:5432 (attempt $i/10)..." -ForegroundColor Gray
    Start-Sleep -Seconds 1
}
if (-not $PostgresReady) {
    Write-Error "PostgreSQL is not reachable on localhost:5432. Please ensure PostgreSQL is running (via Docker Compose or as a local service)."
    exit 1
}
Write-Host "  PostgreSQL is connected on localhost:5432." -ForegroundColor Green

# Check Redis
if (Test-PortOpen -Port 6379) {
    Write-Host "  Redis is connected on localhost:6379." -ForegroundColor Green
} else {
    Write-Warning "  Redis is not reachable on localhost:6379. Application will run with SafeRedisClient fallback."
}

# 4. Check Virtual Environment and Python Dependencies
Write-Host "`n[4/7] Checking Python virtual environment and dependencies..." -ForegroundColor Yellow
$VenvPython = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "  Creating Python virtual environment in backend\.venv..." -ForegroundColor Gray
    & python -m venv (Join-Path $PSScriptRoot "backend\.venv")
}

$DepCheck = & $VenvPython -c "import fastapi, uvicorn, sqlalchemy, redis, psycopg2; print('OK')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing required backend dependencies..." -ForegroundColor Gray
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
}
Write-Host "  Backend dependencies verified." -ForegroundColor Green

# 5. Run Alembic Database Migrations
Write-Host "`n[5/7] Running Alembic database migrations..." -ForegroundColor Yellow
try {
    $BackendDir = Join-Path $PSScriptRoot "backend"
    Push-Location $BackendDir
    & $VenvPython -m alembic -c alembic.ini upgrade head
    Pop-Location
    Write-Host "  Database schema migrations applied successfully." -ForegroundColor Green
} catch {
    Pop-Location -ErrorAction SilentlyContinue
    Write-Error "Alembic migration failed: $_. Verify DATABASE_URL in backend\.env."
    exit 1
}

# 6. Check for Already Running Servers (avoid duplicate servers)
Write-Host "`n[6/7] Checking active server ports..." -ForegroundColor Yellow
$BackendRunning = Test-PortOpen -Port 8000
$FrontendRunning = Test-PortOpen -Port 5173

if ($BackendRunning) {
    Write-Host "  FastAPI backend is already running on http://127.0.0.1:8000." -ForegroundColor Green
} else {
    Write-Host "  Launching FastAPI backend on http://127.0.0.1:8000..." -ForegroundColor Gray
    $BackendDir = Join-Path $PSScriptRoot "backend"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$BackendDir'; & '$VenvPython' -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
}

if ($FrontendRunning) {
    Write-Host "  Vite frontend is already running on http://localhost:5173." -ForegroundColor Green
} else {
    Write-Host "  Launching Vite frontend on http://localhost:5173..." -ForegroundColor Gray
    $FrontendDir = Join-Path $PSScriptRoot "frontend"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$FrontendDir'; npm run dev"
}

# 7. Final Status Display
Write-Host "`n=======================================================" -ForegroundColor Green
Write-Host "ByteLink local development stack is ready!" -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor Cyan
Write-Host "  Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  Database:  postgresql://bytelink:bytelink@localhost:5432/bytelink" -ForegroundColor Gray
Write-Host "  Cache:     redis://localhost:6379/0" -ForegroundColor Gray
Write-Host "=======================================================" -ForegroundColor Green
