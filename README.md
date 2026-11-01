# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener and click analytics application built with modern web technologies: React 19, Vite, FastAPI, PostgreSQL, Redis, and Firebase Authentication. It provides instantaneous link redirections, custom alias creations, password-protected short links, authenticated user dashboards, and real-time geographical and device analytics streaming via WebSockets.

---

## Architecture Overview

| Component | Technology | Local URL | Description |
|---|---|---|---|
| **Frontend** | React 19 + Vite | `http://localhost:5173` | Responsive UI with real-time analytics, QR generator, and Google OAuth |
| **Backend** | FastAPI + Uvicorn | `http://localhost:8000` | Asynchronous REST and WebSocket API with Pydantic validation |
| **API Docs** | Swagger / OpenAPI | `http://localhost:8000/docs` | Interactive API documentation and schema explorer |
| **Database** | PostgreSQL 15/16 | `127.0.0.1:5432` | Relational storage with SQLAlchemy 2.0 and Alembic schema migrations |
| **Cache & Limiter** | Redis 7 | `127.0.0.1:6379` | Response caching, atomic Lua rate limiting, and analytics fallback |
| **Authentication** | Firebase Auth | External | Google OAuth with public key cryptographic RS256 token verification |

---

## Local Development Setup (Windows / Linux / macOS)

### 1. Prerequisites
Ensure the following tools are installed:
- **Python 3.10+ / 3.11+** (`python --version`)
- **Node.js 18+ / 20+ & npm** (`node -v` and `npm -v`)
- **Docker & Docker Compose** (for local PostgreSQL and Redis containers, or running native services)
- **Git** (`git --version`)

### 2. Environment Configuration
Clone the repository and copy the environment configuration templates:

```bash
# Backend environment setup
cp backend/.env.example backend/.env

# Frontend environment setup
cp frontend/.env.example frontend/.env
```

*(On Windows PowerShell, use `Copy-Item backend\.env.example backend\.env` and `Copy-Item frontend\.env.example frontend\.env`).*

#### Key Configuration Variables
- **`backend/.env`**:
  ```ini
  DATABASE_URL=postgresql://bytelink:bytelink@localhost:5432/bytelink
  PUBLIC_BASE_URL=http://localhost:8000
  ENV=development
  CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
  REDIS_URL=redis://localhost:6379/0
  JWT_SECRET=bytelink-super-secret-development-jwt-key-2026-secure
  ALGORITHM=HS256
  ACCESS_TOKEN_EXPIRE_MINUTES=60
  REFRESH_TOKEN_EXPIRE_DAYS=7
  FIREBASE_PROJECT_ID=link-shortener-6c96e
  ENABLE_LEGACY_AUTH=false
  TRUSTED_PROXY_COUNT=0
  ```
  > [!IMPORTANT]
  > `JWT_SECRET` must be at least 32 characters long. The backend fails fast at startup if it is missing or shorter than 32 characters.
  > `ENABLE_LEGACY_AUTH` defaults to `false` for security (legacy password registration/login is disabled).

- **`frontend/.env`**:
  ```ini
  VITE_API_URL=http://localhost:8000
  VITE_FIREBASE_API_KEY=AIzaSyAPeMM2qYyM4moGqcc5bSFjA7tMTJfWPCw
  VITE_FIREBASE_AUTH_DOMAIN=link-shortener-6c96e.firebaseapp.com
  VITE_FIREBASE_PROJECT_ID=link-shortener-6c96e
  VITE_FIREBASE_STORAGE_BUCKET=link-shortener-6c96e.firebasestorage.app
  VITE_FIREBASE_MESSAGING_SENDER_ID=229810061426
  VITE_FIREBASE_APP_ID=1:229810061426:web:3ace5251defedd895182eb
  VITE_FIREBASE_MEASUREMENT_ID=G-LMMSJ9NS4D
  ```

### 3. Automated Local Startup

You can launch the entire stack (PostgreSQL, Redis, migrations, backend, and frontend) with a single command:

- **Windows (PowerShell):**
  ```powershell
  .\start-local.ps1
  ```
- **Windows (Command Prompt):**
  ```cmd
  start-local.bat
  ```
- **Linux / macOS (Bash):**
  ```bash
  chmod +x start-local.sh
  ./start-local.sh
  ```

### 4. Manual Step-by-Step Setup

If you prefer to start each component manually:

#### A. Start Database & Cache
```bash
docker compose up -d postgres redis
```

#### B. Setup Backend & Run Migrations
```bash
cd backend
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt
alembic upgrade head
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

#### C. Setup Frontend
```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Core Security & Reliability Features

### 1. Robust Password Protection (bcrypt + SHA-256 Pre-hashing)
Link password locks are hashed using `bcrypt`. To protect against bcrypt's native 72-byte truncation boundary, passwords are pre-hashed with SHA-256 before bcrypt digest generation. Legacy SHA-256 links are validated using constant-time comparisons (`hmac.compare_digest`) and automatically upgraded to bcrypt upon first successful unlock. Password unlock is strictly rate-limited to 5 attempts per minute per IP and short ID.

### 2. Account Pre-Hijacking Prevention
When a user signs in with Google, account linking to existing PostgreSQL user records requires `email_verified: True` in the verified Firebase ID token claims. Unverified emails reject linking with HTTP 401/409, preventing account takeover attacks.

### 3. Atomic Rate Limiting
Rate limiting uses an atomic Redis Lua script (`INCR` + `EXPIRE`), preventing race conditions and key leakage without expiration. The rate limiter re-raises `HTTPException(429)` cleanly and fails open only when Redis infrastructure is unreachable.

### 4. Injection & XSS Protection
- Custom aliases are validated against `^[A-Za-z0-9_-]{3,50}$` and reserved keywords (`api`, `docs`, `health`, etc.) are rejected.
- Dynamic values rendered in server HTML templates and forms are escaped with `html.escape`.

### 5. Non-Blocking WebSocket Authentication
WebSocket connection for real-time analytics offloads token verification to thread pools without blocking the ASGI event loop. Authentication occurs via the first WebSocket message frame (`{"type": "auth", "token": "..."}`), preventing tokens from leaking in query parameters or server access logs.

### 6. Data Integrity & Concurrency
- `clicks_count` is updated atomically in SQL (`UPDATE urls SET clicks_count = clicks_count + 1 WHERE id = ...`) within the same database transaction that records the `ClickEvent`.
- Database foreign keys specify `ondelete="CASCADE"`.
- URL expiration timestamps are normalized to UTC with past expiration dates rejected at creation time.
- Redis cache records carry an explicit TTL (24 hours or link expiration, whichever is sooner) and are purged immediately when a user deletes a link.

---

## Verification & Testing

### Running the Backend Verification Suite
Backend code formatting, linting, migration check, and all 54 pytest tests must pass:

```bash
cd backend
black --check .
isort --check-only .
ruff check .
pytest -q
alembic check
```

### Running the Frontend Verification Suite
Frontend linting and production build:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) validates every push and pull request to `main`:
1. **Code Formatting & Lint Check**: Validates formatting with `black`, import ordering with `isort`, and code style with `ruff`.
2. **Backend Pytest**: Spins up isolated containerized services (`postgres:15-alpine` and `redis:7-alpine`), runs `alembic upgrade head` and `alembic check`, and runs all 54 pytest unit and integration tests.
3. **Frontend Lint & Build**: Runs `npm run lint` and `npm run build` using Node.js 22.
4. **Docker Image Build Validation**: Validates that `backend/Dockerfile` builds cleanly using a non-root user (`appuser`).
