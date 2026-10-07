# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener application built with modern web technologies. It provides instantaneous link redirections, custom alias creations, password lock protections, user authentication dashboards, and real-time geographical analytics streaming via WebSockets.m

## Run locally

This is the recommended recruiter-demo setup. It runs PostgreSQL and Redis in Docker,
while the FastAPI and Vite development servers run directly on the host.

### One-time setup

1. Install Docker Desktop, Python 3.11+, Node.js 22+, and Git.
2. Copy the environment templates:

   ```powershell
   Copy-Item backend\.env.example backend\.env
   Copy-Item frontend\.env.example frontend\.env
   ```

3. In `backend\.env`, fill in `JWT_SECRET`, the Firebase Admin credentials, and
   confirm `PUBLIC_BASE_URL=http://localhost:8000`, `ENV=development`, and the local
   `DATABASE_URL`/`REDIS_URL` values. Firebase web-app values belong in
   `frontend\.env`. Never commit either `.env` file.
4. Install dependencies:

   ```powershell
   python -m venv backend\.venv
   backend\.venv\Scripts\Activate.ps1
   pip install -r backend\requirements.txt
   cd frontend
   npm install
   cd ..
   ```

### Start the demo

Run each command in a separate terminal:

```powershell
docker compose up -d postgres redis
cd backend
..\backend\.venv\Scripts\python.exe -m alembic upgrade head
..\backend\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`. The API is at `http://localhost:8000/docs` and its
health check is `http://localhost:8000/health`. On later demo runs, only
`docker compose up -d postgres redis`, the migration command, and the two server
commands are needed. The optional `start-local.bat` and `start-local.sh` scripts
automate those steps after the one-time setup.

### Required environment variables

Backend: `DATABASE_URL`, `PUBLIC_BASE_URL`, `ENV`, `CORS_ALLOWED_ORIGINS`,
`REDIS_URL`, `JWT_SECRET`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`REFRESH_TOKEN_EXPIRE_DAYS`, and Firebase Admin credentials
(`FIREBASE_PROJECT_ID` plus `FIREBASE_CLIENT_EMAIL` and `FIREBASE_PRIVATE_KEY`, or
one of the documented service-account alternatives). Frontend: `VITE_API_URL` and
the `VITE_FIREBASE_*` web-app values. Safe placeholders are in
[`backend/.env.example`](backend/.env.example) and
[`frontend/.env.example`](frontend/.env.example).

### Second-device mode without deployment

#### Option A: same Wi-Fi/LAN

1. Find this computer's LAN IPv4 address:

   ```powershell
   ipconfig
   ```

   Use the `IPv4 Address` from the active Wi-Fi/Ethernet adapter, for example
   `192.168.1.25`.
2. Change only `PUBLIC_BASE_URL` in `backend\.env` to
   `http://192.168.1.25:8000`. Development CORS automatically adds the matching
   Vite origin (`http://192.168.1.25:5173`).
3. Restart the backend with:

   ```powershell
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

4. If Windows prompts or blocks it, allow Python/Uvicorn on **Private networks** in
   Windows Defender Firewall. You can also add an inbound TCP rule for ports 8000
   and 5173 in **Windows Defender Firewall with Advanced Security**.
5. On the phone or laptop connected to the same Wi-Fi, open
   `http://192.168.1.25:5173`. Short links use the LAN backend URL.

#### Option B: temporary free tunnel

Install either [ngrok](https://ngrok.com/) or
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

With ngrok:

```powershell
ngrok http 8000
```

With Cloudflare's temporary tunnel:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Copy the generated `https://...` URL into `PUBLIC_BASE_URL` in `backend\.env`,
restart the backend, and create a new short link. Open that short link from the
phone using mobile data (Wi-Fi disabled) to verify the tunnel. The tunnel is
temporary and its URL may change each time it starts. The frontend can remain on
the demo computer at `http://localhost:5173`; its API calls use `VITE_API_URL`.
The backend builds `ws://` for HTTP URLs and `wss://` for HTTPS tunnel URLs.

Switching between localhost, LAN, and tunnel modes requires changing only
`PUBLIC_BASE_URL` and restarting the backend. The frontend WebSocket and short-link
URLs follow that backend base URL.

### Recruiter demo script

1. Sign in with Google.
2. Paste a long GitHub URL, such as a repository README or a URL with query
   parameters, and create a short link.
3. Copy the generated link, open it in a new browser tab, and show that it redirects.
4. Open the same link on a phone in LAN mode or on mobile data in tunnel mode.
5. Return to the analytics page and show the click count, device/referrer data, and
   live dashboard update through the WebSocket.

Create two or three seed links before the demo so the dashboard is not empty:
the GitHub repository, a long GitHub issue URL, and a long documentation URL. Open
each once from the browser and once from the phone.

## Access model

Browsing is public: the homepage, informational content, and every valid short URL can
be opened without an account. Short URL resolution never uses authentication and
continues to redirect visitors (or show the existing link-password prompt).

Account-owned usage requires authentication. Creating links, opening the dashboard,
listing or deleting links, and viewing analytics require a bearer access token. The
frontend protects private routes centrally and preserves the requested route through
login/signup. The backend independently validates the token and filters link and
analytics data by the authenticated user's `user_id`.

---

## Features

| Feature | Description |
|---|---|
| **User Accounts & JWT Auth** | Secure registration, token-based login, automatic access token refreshing via refresh tokens |
| **Live Analytics Dashboard** | Track clicks, top countries, devices, and real-time logs via WebSockets |
| **Advanced Shortening Options** | Custom aliases, link expiry timers, bcrypt-encrypted password protection |
| **QR Code Generator** | Built-in canvas-rendered QR codes with PNG download |
| **Caching & Rate Limiting** | High-speed Redis-backed caching with graceful in-memory fallback |
| **Explicit CORS Configuration** | Browser origins are configured through the backend environment |
| **Professional API Landing** | Async `/` route returning health and endpoint metadata instead of a 404 |
| **Robust Validation Errors** | Frontend formats FastAPI list-based validation errors into human-readable strings |
| **Direct bcrypt Hashing** | Removed deprecated `passlib` wrapper; uses `bcrypt` directly for full Python 3.11+ compatibility |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite, Axios, Chart.js, Lucide Icons, Framer Motion |
| **Backend** | FastAPI 0.137+, Python 3.11, Uvicorn, WebSockets, Background Tasks |
| **Database** | PostgreSQL, SQLAlchemy 2.0 ORM, Alembic Migrations |
| **Cache / Rate Limit** | Redis (Upstash TLS), SafeRedisClient fallback |
| **Containerization** | Docker, Docker Compose |
| **CI/CD** | GitHub Actions (lint, test, build, Docker verify) |
| **Hosting** | Render (Backend + DB + Redis), Vercel (Frontend SPA) |

---

## Folder Structure

```text
Link-Shortener/
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD pipeline (checkout@v4, python@v5, node@v4)
├── backend/
│   ├── alembic/                # Database schema migration versions
│   ├── alembic.ini             # Alembic configuration
│   ├── main.py                 # FastAPI app — routes, middleware, CORS, error handlers
│   ├── database.py             # SQLAlchemy engine & Session dependency
│   ├── models.py               # ORM models for PostgreSQL
│   ├── security.py             # JWT token management & direct bcrypt hashing
│   ├── redis_client.py         # SafeRedisClient with in-memory MockRedis fallback
│   ├── test_main.py            # Pytest unit tests (10 tests)
│   ├── requirements.txt        # Modernized Python dependency stack
│   ├── runtime.txt             # Pins Python 3.11.11 for Render
│   ├── Dockerfile              # Slim Python 3.11 Docker image
│   └── Procfile                # Web process command for PaaS platforms
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── axios.js        # Axios instance with JWT + refresh token interceptors
│   │   ├── components/
│   │   │   ├── ShortenerForm.jsx       # Hero panel, shortener form, live preview
│   │   │   ├── AnalyticsDashboard.jsx  # Click charts, geo logs, WebSocket live updates
│   │   │   ├── Dashboard.jsx           # User links history management
│   │   │   ├── SignIn.jsx              # Auth register/login form
│   │   │   ├── MagnetLines.jsx         # Interactive magnetic lines animation
│   │   │   ├── TextRepel.jsx           # Mouse-repel text animation
│   │   │   └── ErrorBoundary.jsx       # React error boundary with fallback UI
│   │   ├── App.jsx             # Route declarations & navigation bar
│   │   └── index.css           # HSL CSS variable design system & animations
│   ├── eslint.config.js        # ESLint flat config (motion JSX scoped, hooks rules)
│   ├── vercel.json             # SPA catch-all rewrite rule for client-side routing
│   └── package.json            # Frontend dependencies
├── pyproject.toml              # Black & Isort profile compatibility config
├── docker-compose.yml          # Local multi-container orchestration
├── render.yaml                 # Render Web Service blueprint (Neon remains external)
└── README.md
```

---

## Dependency Versions

### Backend (Key Packages)

| Package | Version |
|---|---|
| `fastapi` | ≥ 0.137 |
| `pydantic` | ≥ 2.13 |
| `sqlalchemy` | ≥ 2.0.51 |
| `alembic` | ≥ 1.18 |
| `uvicorn[standard]` | ≥ 0.49 |
| `bcrypt` | ≥ 5.0 |
| `redis` | ≥ 8.0 |
| `psycopg2-binary` | ≥ 2.9.12 |
| `python-jose[cryptography]` | ≥ 3.3 |

### Frontend (Key Packages)

| Package | Version |
|---|---|
| `react` | ^19 |
| `vite` | ^8 |
| `axios` | ^1.14 |
| `motion` | ^12 |
| `chart.js` | ^4.5 |
| `react-router-dom` | ^7 |
| `lucide-react` | ^1.7 |

---

## Environment Variables

### Backend (`backend/.env`)

```env
# Base URL of the deployed FastAPI server (used in short URL generation)
PUBLIC_BASE_URL=http://localhost:8000

# Neon PostgreSQL connection string (backend only)
DATABASE_URL=postgresql://USER:PASSWORD@EP-example-pooler.us-east-2.aws.neon.tech/DATABASE?sslmode=require

# Redis connection string. Use redis:// locally and rediss:// for managed TLS Redis.
REDIS_URL=rediss://default:password@host:6379

# JWT signing secret (generate a strong random key in production)
# JWT_SECRET must be configured in the backend environment.

# JWT algorithm
ALGORITHM=HS256

# Access token lifetime in minutes
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Allowed frontend origin(s) — comma-separated for multiple origins
# Exact browser origin(s), comma-separated
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Application environment
ENV=development
```

### Frontend (`frontend/.env`)

```env
# Full URL of the deployed backend (no trailing slash)
VITE_API_URL=http://localhost:8000
```

---

## Local Setup & Run

### Prerequisites
- Python 3.11+
- Node.js 22+
- Neon PostgreSQL
- Redis (local or cloud e.g. Upstash)

### 1. Database Migrations

```bash
cd backend
alembic upgrade head
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Activate virtual environment:
# Windows:
.\.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

| Endpoint | URL |
|---|---|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| Health Check | `http://localhost:8000/health` |
| API Root | `http://localhost:8000/` |

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

- App: `http://localhost:5173`

---

## CI/CD Pipeline

The project uses a fully automated GitHub Actions pipeline (`.github/workflows/deploy.yml`) that runs on every push or pull request to `main`.

### Pipeline Jobs

| Job | Description |
|---|---|
| `code-quality-and-lint` | Runs `black --check`, `isort --check-only`, `ruff check` on the backend |
| `backend-test` | Spins up Postgres & Redis services, runs `pytest backend/` |
| `frontend-build` | Runs `npm ci` then `npm run build` inside `frontend/` |
| `docker-verify` | Builds the backend Docker image without pushing |

### Action Versions

| Action | Version |
|---|---|
| `actions/checkout` | v4 |
| `actions/setup-python` | v5 (Python 3.11) |
| `actions/setup-node` | v4 (Node.js 22) |
| `docker/setup-buildx-action` | v2 |
| `docker/build-push-action` | v4 |

### Local Code Quality Commands

Run these before every commit:

```bash
# Python formatting & linting
black backend/
isort backend/
ruff check backend/ --fix

# Verify (what CI runs)
black --check backend/
isort --check-only backend/
ruff check backend/

# Frontend lint & build
cd frontend
npm run lint
npm run build
```

---

## Running Tests

```bash
pytest backend/
```

Runs 10 tests covering:
- User registration & login
- Invalid email validation
- URL shortening (anonymous + authenticated)
- Custom alias creation & conflict detection
- Password-protected links
- Health check endpoint
- Root landing endpoint

---

## CORS Configuration

In development, the backend allows the local Vite origins. In production,
`CORS_ALLOWED_ORIGINS` is required and must contain the exact deployed frontend
origin(s), comma-separated. Wildcard origins are not used because authenticated
browser requests use credentials.

---

## Docker Compose

The Compose file provides local PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

The backend reads `DATABASE_URL` and `REDIS_URL` from `backend/.env`. The backend
container remains available for containerized checks, but the recommended demo runs
Uvicorn and Vite on the host so reloads and LAN/tunnel switching are straightforward.

## Production notes

This project is intentionally being demonstrated locally. In a real deployment,
`PUBLIC_BASE_URL` would be a public HTTPS domain owned by the application, for
example `https://short.example.com`, and `ENV=production` would enforce HTTPS.
The existing [`render.yaml`](render.yaml) describes the FastAPI deployment and the
existing Vercel configuration supports the frontend SPA. Production would also use
managed PostgreSQL/Redis, a secret `JWT_SECRET`, production Firebase Admin
credentials, and exact deployed frontend origins in `CORS_ALLOWED_ORIGINS`.
Localhost and temporary tunnel URLs are not suitable as permanent public links.

## Demo verification checklist

- [ ] `docker compose up -d postgres redis` starts both healthy services.
- [ ] `alembic upgrade head` completes successfully.
- [ ] `http://localhost:5173` loads and Google sign-in succeeds.
- [ ] A created short link redirects to its long URL.
- [ ] The click appears in the analytics dashboard.
- [ ] The dashboard updates live, or its polling fallback refreshes it.
- [ ] The short link opens from a phone in LAN or tunnel mode.
- [ ] `pytest backend/` passes (database-dependent tests run when PostgreSQL is available).
- [ ] `cd frontend; npm run lint; npm run build` passes.

---

## Cloud Deployment

### Render Web Service

The `render.yaml` blueprint provisions only the backend web service. Neon
PostgreSQL remains the only production database. Redis is an external
cache/rate-limit service and must be configured separately.

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |

Set these environment variables in Render:

- `DATABASE_URL` — Neon PostgreSQL URL with `sslmode=require`
- `REDIS_URL` — external Redis provider URL (`redis://` or preferably `rediss://`
  for TLS). Do not set this to `localhost` or `redis://redis:6379/0` on Render.
- `JWT_SECRET` — a strong secret stored only in Render
- `PUBLIC_BASE_URL` — the deployed Render HTTPS backend URL used by short URLs and QR codes
- `CORS_ALLOWED_ORIGINS` — exact deployed frontend origin(s), comma-separated
- `ALGORITHM=HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES=60`
- `REFRESH_TOKEN_EXPIRE_DAYS=7`
- `ENV=production`

Run `alembic upgrade head` once from a protected environment with the same
`DATABASE_URL` before serving production traffic. Do not run destructive schema
commands against production.

### Vercel (Frontend)

1. Import repository on Vercel, set **Root Directory** to `frontend`.
2. Vercel auto-detects Vite; no build command changes needed.
3. Add environment variable:
   - `VITE_API_URL` → your Render backend URL (e.g. `https://link-shortener-backend.onrender.com`)
4. The `vercel.json` rewrite rule ensures client-side routing works for all routes.

---

## Security Notes

- JWT tokens are signed with `HS256` using the backend-only `JWT_SECRET` environment variable.
- Passwords are hashed using `bcrypt` directly (no deprecated wrapper libraries).
- Link passwords use SHA-256 before bcrypt to avoid bcrypt's 72-byte input limit.
- The application remains available in degraded mode if Redis is temporarily
  unavailable, but caching and distributed rate limiting require a reachable
  external Redis service.
- Rate limiting is enforced per-IP via Redis counters.
