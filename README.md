# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener application built with modern web technologies. It provides instantaneous link redirections, custom alias creations, password lock protections, user authentication dashboards, and real-time geographical analytics streaming via WebSockets.

## Live Demo

- **Web Application**: [https://bytelink-demo.example.com](https://bytelink-demo.example.com) *(Recruiter Demo Placeholder — update with your deployed URL)*
- **Interactive API Docs (Swagger UI)**: [https://bytelink-demo.example.com/docs](https://bytelink-demo.example.com/docs)
- **Live System Metrics Endpoint**: [https://bytelink-demo.example.com/api/metrics](https://bytelink-demo.example.com/api/metrics)

---

## System Architecture

```mermaid
flowchart TD
    subgraph Clients["Clients & Presentation"]
        User["Browser Client"]
        DevClient["API / CLI Client"]
        WSClient["Analytics Dashboard (WebSocket)"]
    end

    subgraph API["FastAPI Application (main.py)"]
        RateLimit["Sliding-Window Limiter\n(Atomic Lua Script)"]
        RedirectEP["GET /:short_id\n(Redirect Handler)"]
        ShortenEP["POST /api/shorten\n(Collision-Safe Creator)"]
        APIKeyEP["API Key Auth & Management"]
        PubSubListener["Redis Pub/Sub Listener Task"]
    end

    subgraph CacheLayer["In-Memory Cache & Message Broker (Redis)"]
        RedisCache["Redis URL Cache & ZSET Rate Limiters"]
        RedisMetrics["Redirect Counters & Metrics"]
        RedisStream["Redis Streams (stream:clicks)\n+ Dead-Letter Stream"]
        RedisPubSub["Redis Pub/Sub (channel:ws:clicks)"]
    end

    subgraph Storage["Relational Storage (PostgreSQL 18)"]
        PostgresDB[("PostgreSQL\n- users & api_keys\n- urls (max_clicks, active)\n- click_events\n- link_reports")]
    end

    subgraph WorkerService["Asynchronous Analytics Worker (worker.py)"]
        WorkerConsumer["Consumer Group Reader\n(XREADGROUP / XAUTOCLAIM)"]
        GeoUAParser["GeoIP & User-Agent Parser"]
        BatchWriter["Batch Inserter & Deduplicator\n(At-Least-Once Guarantee)"]
    end

    %% Redirect Flow
    User -->|1. GET /:short_id| RateLimit
    RateLimit -->|Check rolling window| RedisCache
    RateLimit -->|Allowed| RedirectEP
    RedirectEP -->|2. Fast Cache Lookup| RedisCache
    RedirectEP -.->|Cache Miss Fallback| PostgresDB
    RedirectEP -->|3. Non-blocking XADD| RedisStream
    RedirectEP -->|4. Increment hit/miss metrics| RedisMetrics
    RedirectEP -->|5. 302 Redirect Location| User

    %% Shorten Flow
    DevClient -->|POST /api/shorten\n(Bearer / X-API-Key)| ShortenEP
    ShortenEP -->|Auth check| PostgresDB
    ShortenEP -->|Optimistic Insert + Retry on Conflict| PostgresDB
    ShortenEP -->|Populate Cache| RedisCache

    %% Async Worker Stream Processing Flow
    RedisStream -->|6. Batch Read| WorkerConsumer
    WorkerConsumer --> GeoUAParser
    GeoUAParser --> BatchWriter
    BatchWriter -->|7. Batch INSERT & atomic counter| PostgresDB
    BatchWriter -->|8. XACK / Retry / Dead-Letter| RedisStream
    BatchWriter -->|9. Publish Live Click Update| RedisPubSub

    %% WebSocket Flow
    RedisPubSub -->|Pub/Sub Message| PubSubListener
    PubSubListener -->|Live Broadcast| WSClient
```

---

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

## Short Code Generation & Keyspace Analysis

ByteLink generates 7-character alphanumeric short codes using a Base62 alphabet (`[a-zA-Z0-9]`).

### Keyspace Math
- **Alphabet Size**: 62 characters (26 lowercase + 26 uppercase + 10 digits)
- **Code Length**: $L = 7$
- **Total Unique Keyspace**:
  $$N = 62^7 = 3,521,614,606,208 \approx 3.52 \times 10^{12} \text{ (over 3.52 trillion unique combinations)}$$

### Collision Probability & Birthday Paradox
When generating random keys uniformly, collision probability can be evaluated from two perspectives:
1. **Per-Insertion Collision Probability**: The probability that a freshly generated short code matches an existing key in a database of $n$ links:
   $$P(\text{collision on next insert}) = \frac{n}{N}$$
   - **At 1,000,000 (1M) links**: $\frac{10^6}{3.52 \times 10^{12}} \approx 0.0000284\%$ (~1 in 3,520,000 insertions).
   - **At 100,000,000 (100M) links**: $\frac{10^8}{3.52 \times 10^{12}} \approx 0.00284\%$ (~1 in 35,216 insertions).

2. **Dataset-Wide Birthday Paradox**: The probability of at least one collision occurring across the entire dataset of $n$ randomly generated keys:
   $$P(\ge 1 \text{ collision}) \approx 1 - e^{-\frac{n(n-1)}{2N}} \approx 1 - e^{-\frac{n^2}{2N}}$$
   - **At 1,000,000 (1M) links**: $\frac{n^2}{2N} = \frac{10^{12}}{7.043 \times 10^{12}} \approx 0.14197 \implies P \approx 13.24\%$.
   - **At 100,000,000 (100M) links**: $\frac{n^2}{2N} \approx 1420 \implies P \approx 100\%$.

### Concurrency-Safe Retry vs. Check-Then-Insert
Rather than using a vulnerable "check-then-insert" pattern (`SELECT` before `INSERT`), which causes race conditions under concurrent creation and adds redundant database round-trip latency to 99.997%+ of requests, ByteLink relies on PostgreSQL's atomic `UNIQUE` constraint index on `short_id`. The application optimistically attempts insertion; in the rare event of an `IntegrityError`, the transaction is cleanly rolled back and retried up to 5 times with a new pseudo-random draw.

---

## Redirect Status Codes & HTTP Semantics (301 vs 302)

ByteLink supports configurable HTTP redirect status codes via the `REDIRECT_STATUS_CODE` environment variable (default: `302`). Both `GET` and `HEAD` requests to `/{short_id}` are handled symmetrically.

| Status Code | Caching Behavior | Analytics Impact | Use Case |
|---|---|---|---|
| **`302 Found` (Default)** | Temporary redirect; browsers and proxies do **not** cache the destination. | **Full Accuracy**: Every click reaches ByteLink, enabling real-time analytics, geo-logging, sliding-window rate limiting, and instant enforcement of `max_clicks` and link expiration. | Recommended for URL shorteners requiring precise click metrics and administrative link controls. |
| **`301 Moved Permanently`** | Permanent redirect; browsers aggressively cache the destination locally on disk. | **Blinded Analytics**: Subsequent visits bypass ByteLink servers entirely; clicks are neither counted nor logged, and link edits or deactivations are ignored by cached browsers. | Recommended when prioritizing server bandwidth and latency offloading over click tracking. |

`HEAD` requests return the exact same HTTP redirect status code and `Location` header without transmitting a response body or incrementing user click limits.

---

## System Capacity & Resource Estimates

### Workload Assumptions & Traffic Profile
- **Read-to-Write Ratio**: 10:1 (read-heavy, representative of high-throughput URL shortening services).
- **Target Traffic**:
  - Average Read QPS: **1,000 req/s** (~86.4M redirects/day)
  - Average Write QPS: **100 req/s** (~8.64M links created/day)
  - Peak Read Traffic (2x headroom): **2,000 req/s**

### Storage Footprint per Record
1. **URL Record (`urls` table)**:
   - Primary Key `id`: 4 bytes
   - `short_id` VARCHAR(50): ~10 bytes avg
   - `target_url` VARCHAR: ~150 bytes avg
   - `clicks_count` INT: 4 bytes
   - `created_at` / `expires_at` TIMESTAMP: 16 bytes
   - `password` SHA-256 hash: 64 bytes
   - `max_clicks` INT, `is_active` BOOL, `user_id` INT: 9 bytes
   - Row overhead + B-tree indexes (`short_id` unique, `user_id`): ~150 bytes
   - **Total per URL**: $\approx 500\text{ bytes}$

2. **Click Event Record (`click_events` table)**:
   - `id`: 4 bytes
   - `url_id` INT: 4 bytes
   - `ip_address` VARCHAR(50): ~15 bytes
   - `country`, `city` VARCHAR(50): ~30 bytes
   - `lat`, `lon` FLOAT: 16 bytes
   - `user_agent`, `browser`, `os`, `device`: ~100 bytes
   - `clicked_at` TIMESTAMP: 8 bytes
   - Row overhead + Foreign Key index: ~80 bytes
   - **Total per Click Event**: $\approx 257\text{ bytes} \approx 250\text{ bytes}$

### Annual Storage Growth Projections
- **URLs**: $10,000,000\text{ links/year} \times 500\text{ bytes} \approx 5.0\text{ GB/year}$
- **Clicks**: $100,000,000\text{ clicks/year} \times 250\text{ bytes} \approx 25.0\text{ GB/year}$
- **Total Relational Database Storage**: $\approx 30.0\text{ GB/year}$ (readily accommodates cost-effective managed NVMe storage).

### In-Memory Redis Cache Budget (80/20 Pareto Working Set)
- Following the Pareto Principle, 20% of short links generate 80% of total redirect volume.
- In-memory working set for 2,000,000 hot URLs:
  $$2,000,000 \times 500\text{ bytes} \approx 1.0\text{ GB RAM}$$
- Redis Stream buffer (`stream:clicks` trimmed with `MAXLEN ~ 100,000` entries): $\approx 50\text{ MB RAM}$.
- Total Redis memory footprint: **$\le 2\text{ GB}$**, fitting comfortably on entry-level cloud cache tiers.

---

## Design Decisions & Trade-Offs

### 1. Redis Streams Worker vs. Heavyweight Message Broker (Kafka / Celery / RabbitMQ)
- **Decision**: Decoupled consumer group worker (`backend/worker.py`) running on Redis Streams (`stream:clicks`).
- **Rationale**: URL redirect latency must remain sub-50ms. Processing GeoIP resolution, user-agent parsing, and PostgreSQL writes synchronously inside the redirect handler degrades throughput and exhausts DB connection pools under load.
- **Trade-Off**: Rather than introducing an entirely new operational dependency (e.g. Kafka or RabbitMQ with Celery workers), Redis Streams leverages the existing Redis infrastructure. It provides at-least-once delivery, consumer groups, consumer failure recovery (`XAUTOCLAIM`/`XCLAIM`), batching, and dead-letter queues (`stream:clicks:dead`) with sub-millisecond `XADD` write latency.

### 2. Sliding-Window Rate Limiting via Redis Sorted Sets & Atomic Lua
- **Decision**: Sorted set (ZSET) timestamp scoring inside an atomic Lua script.
- **Rationale**: Standard fixed-window counter limiters are vulnerable to traffic spikes (up to 2x configured limit) at the boundaries of time windows.
- **Trade-Off**: Storing individual request timestamps in a ZSET uses slightly more Redis memory than a single integer counter, but completely eliminates boundary burst vulnerability while atomic Lua execution avoids multi-command round-trip race conditions.

### 3. HTTP Redirect Status Codes: 302 Found vs. 301 Moved Permanently
- **Decision**: Configurable via `REDIRECT_STATUS_CODE`, defaulting to `302 Found`. `HEAD` requests match symmetrically.
- **Trade-Off**:
  - `301 Moved Permanently` allows client browsers to aggressively cache target URLs on disk, reducing subsequent server requests. However, it blinds the analytics engine to repeat clicks and prevents real-time enforcement of link deactivations, edits, or `max_clicks` limits.
  - `302 Found` forces browsers to re-query ByteLink on every click, guaranteeing 100% accurate geolocation tracking, rate limiting, and instant control over link lifecycle.

### 4. Optimistic Insertion with Retry on Conflict vs. Check-Then-Insert
- **Decision**: Rely on PostgreSQL's atomic `UNIQUE` constraint on `short_id`, catching `IntegrityError` to retry on rare collisions.
- **Rationale**: "Check-then-insert" (`SELECT` then `INSERT`) suffers from concurrency race conditions and incurs an unnecessary database `SELECT` round-trip on every single link creation.
- **Trade-Off**: In our $62^7 \approx 3.52\text{ trillion}$ keyspace, the probability of collision is less than 0.003% even with 100M links. Optimistic insert executes in a single database operation for 99.997%+ of requests while guaranteeing absolute correctness under concurrency.

### 5. Cryptographically Hashed API Keys (SHA-256)
- **Decision**: Store only `hashlib.sha256(raw_key).hexdigest()` in PostgreSQL; show the raw secret key (`bl_live_...`) to the user exactly once upon generation.
- **Trade-Off**: Keys cannot be retrieved or recovered if lost (users must generate a new key), but compromised database snapshots or SQL injections expose zero plaintext credentials.

### 6. Fail-Open Architecture for Redis Outages
- **Decision**: In the event of Redis downtime, rate limiting, caching, and stream ingestion gracefully fail open.
- **Rationale**: Transient cache failures must never prevent legitimate end users from reaching their destination links. Redirection falls back transparently to direct PostgreSQL lookups and in-process background tasks.

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
│   ├── test_main.py            # Pytest unit and integration tests (37 tests)
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
JWT_SECRET=<YOUR_SECURE_RANDOM_JWT_SECRET>

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

Runs 37 comprehensive unit and integration tests covering:
- User registration, login, and token refreshing (JWT + direct bcrypt)
- Malformed payloads and invalid email validation
- URL shortening with optimistic concurrency and retry on collision
- Custom alias creation, unique constraint enforcement, and conflict detection
- Password-protected links and SHA-256 pre-hashing
- Sliding-window rate limiting (atomic Redis sorted sets + Lua script) and fail-open resilience
- Link lifecycle management: `max_clicks` atomic enforcement (cache and DB paths), link editing, and disablement
- Durable async click analytics via Redis Streams producer/consumer, worker batching, deduplication, and dead-letter queues
- Abuse protection: SSRF rejection (localhost, private RFC 1918 IPs, public base URL host) and configurable domain blocklist
- Abuse reporting: distinct IP report aggregation and automatic link deactivation threshold
- Configurable redirect status codes (default 302, 301 override) and symmetrical HEAD request handling
- API key lifecycle: creation, SHA-256 hashed storage, listing, Bearer/X-API-Key auth, and revocation
- Health check and API root landing metadata endpoints

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
