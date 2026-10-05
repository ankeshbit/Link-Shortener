# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener application built with modern web technologies. It provides instantaneous link redirections, custom alias creations, password lock protections, user authentication dashboards, and real-time geographical analytics streaming via WebSockets.

## Database: Neon PostgreSQL

Neon PostgreSQL is the application's single database source of truth. The backend
uses SQLAlchemy with the PostgreSQL driver and Alembic migrations; no local database
container is required.

1. Copy `backend/.env.example` to `backend/.env`.
2. Set the backend-only `DATABASE_URL` to the Neon connection string, including
   `?sslmode=require`.
3. Run `alembic upgrade head` from `backend`.
4. Start the backend and frontend using the existing commands below.

Never put `DATABASE_URL` in frontend environment variables, source code, logs, or
version control. Back up existing data before pointing the application at a new Neon
database or branch. The initial migration creates the existing `users`, `urls`, and
`click_events` tables with their ownership and cascade relationships.

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
| **Dynamic CORS Wildcards** | All `*.vercel.app` preview deployments automatically allowed via regex origin matching |
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
├── render.yaml                 # Render infrastructure blueprint
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

# Redis connection string — use rediss:// for TLS (required for Upstash)
REDIS_URL=rediss://default:password@host:6379

# JWT signing secret (generate a strong random key in production)
# JWT_SECRET must be configured in the backend environment.

# JWT algorithm
ALGORITHM=HS256

# Access token lifetime in minutes
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Allowed frontend origin(s) — comma-separated for multiple origins
# Note: all *.vercel.app origins are automatically allowed via regex regardless of this value
FRONTEND_URL=http://localhost:5173

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

The backend is configured to accept requests from:

- `http://localhost:5173` — local Vite dev server
- `http://127.0.0.1:5173` — alternative localhost
- Any URL matching `https://*.vercel.app` — all Vercel deployments (production + previews)
- Any comma-separated URL set in the `FRONTEND_URL` environment variable

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,                        # localhost + FRONTEND_URL list
    allow_origin_regex=r"https://.*\.vercel\.app",# all Vercel preview URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

> **Why regex?** Vercel generates random subdomains for branch preview deployments (e.g. `project-git-feature-xyz-team.vercel.app`). A static `allow_origins` list cannot cover these. The regex pattern matches any secure Vercel subdomain dynamically.

---

## Docker Compose

Boot the backend and Redis locally while connecting to Neon PostgreSQL:

```bash
docker-compose up --build
```

The backend reads DATABASE_URL from backend/.env; only Redis runs as a local container.

---

## Cloud Deployment

### Render (Backend + Redis)

1. Connect your GitHub repository to Render.
2. Apply the `render.yaml` blueprint — it automatically provisions:
   - **Web Service:** FastAPI (Python 3.11)
   - **Redis Instance:** Internal TLS connection
   - **Neon PostgreSQL:** Set `DATABASE_URL` as a protected environment variable
3. In the Render dashboard, set the following environment variables manually:
   - `JWT_SECRET` → a strong secret stored only in Render
   - `FRONTEND_URL` → your Vercel deployment URL (e.g. `https://bytelink.vercel.app`)
   - `PUBLIC_BASE_URL` → your Render web service HTTPS URL (for example, `https://link-shortener-backend.onrender.com`). This is the URL encoded into generated QR codes.
4. Run `alembic upgrade head` from the backend directory as a one-off migration step against Neon before the first production deploy, or run it from a protected deployment job.
5. Trigger a manual deploy or push to `main`.

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
- Redis connection uses TLS (`rediss://`) in production via Upstash.
- Rate limiting is enforced per-IP via Redis counters.