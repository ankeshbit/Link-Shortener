# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener application built with modern web technologies. It provides instantaneous link redirections, custom alias creations, password lock protections, user authentication dashboards, and real-time geographical analytics streaming via WebSockets.

---

## Features
- **User Accounts & JWT Auth:** Secure registration, token-based login, automatic access token refreshing, and Google OAuth compatibility.
- **Asymmetrical Live Analytics Dashboard:** Track click frequencies, top countries, and real-time logs.
- **WebSocket-Based Updates:** Stats update dynamically on the screen as clicks happen.
- **Advanced Shortening Options:** Custom short path aliases, link expiration date timers, and sha256-encrypted password protection.
- **QR Code Generator:** Scan short links instantly using built-in canvas graphics.
- **Caching & Rate Limiting:** High-speed cached reads and client rate limits powered by Upstash/Redis.
- **Dynamic CORS Wildcards:** Support for Vercel preview URLs out-of-the-box using regex-based origin validation.
- **Robust Error Validation Formatting:** Prevents frontend crashes when the API returns list-based validation exceptions by converting them to human-readable strings.
- **Obsolete Hashing Swaps:** Swapped the deprecated `passlib` wrapper for direct, high-performance `bcrypt` hashing.
- **Professional API Landing:** An asynchronous root route (`/`) returning health and metadata instead of a 404.

---

## Tech Stack
*   **Frontend:** React 19 (Vite, Axios, Chart.js, Lucide-React, Framer Motion)
*   **Backend:** FastAPI (Python 3.11, Uvicorn, WebSockets, Background Tasks)
*   **Database:** PostgreSQL (production & local), Alembic Migrations, SQLAlchemy ORM
*   **Caching & Limit Store:** Redis Cache (with SafeRedisClient fallback)
*   **Containerization:** Docker & Docker Compose
*   **Hosting Runtimes:** Railway / Render (Backend/DB/Redis), Vercel (Frontend SPA)
*   **CI/CD:** Upgraded GitHub Actions Pipelines (linting, tests, build checks, and Docker builds)

---

## Folder Structure
```text
Link-Shortener/
├── .github/workflows/
│   └── deploy.yml          # Modernized CI/CD workflow pipeline
├── backend/
│   ├── alembic/            # Database schema migration versions
│   ├── alembic.ini         # Alembic configuration
│   ├── main.py             # FastAPI entrypoint, middlewares, routers & exceptions
│   ├── database.py         # SQLAlchemy engine connection & Session dependency
│   ├── models.py           # SQL DB Schema models (Postgres)
│   ├── security.py         # JWT tokens & direct bcrypt password hashing
│   ├── redis_client.py     # Resilient Redis engine wrapper
│   ├── test_main.py        # PyTest automated unit tests
│   ├── requirements.txt    # Modernized Python dependencies list
│   ├── Dockerfile          # Optimized FastAPI Docker build config
│   └── Procfile            # Deployment web process profile
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── axios.js    # Custom Axios client with JWT refresh interceptor
│   │   ├── components/
│   │   │   ├── ErrorBoundary.jsx       # Fallback UI for React runtime errors
│   │   │   ├── ShortenerForm.jsx       # Shortener panel & live preview charts
│   │   │   ├── AnalyticsDashboard.jsx  # Geographic graphs & WS listener
│   │   │   ├── Dashboard.jsx           # User's links history manager
│   │   │   └── SignIn.jsx              # Auth credentials register/login card
│   │   ├── App.jsx         # App router maps & Navigation
│   │   └── index.css       # Custom HSL CSS variables & animations
│   ├── vercel.json         # SPA router redirect rule
│   ├── eslint.config.js    # ESLint flat configuration (JSX scoped ignores)
│   └── package.json        # Frontend dependencies list
├── pyproject.toml          # Root-level configuration for Python tools (Black, Isort)
├── docker-compose.yml      # Multi-container local workspace orchestrator
├── render.yaml             # Render infrastructure configuration
└── README.md               # Professional documentation
```

---

## Environment Variables

### Backend (`backend/.env`)
Create a `.env` file in the `backend/` folder:
```env
BASE_URL=http://localhost:8000
DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/bytelink
REDIS_URL=rediss://default:password@host:port # Use rediss:// for secure/Upstash connections
SECRET_KEY=your-jwt-signing-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
FRONTEND_URL=http://localhost:5173
ENV=development
```

### Frontend (`frontend/.env`)
Create a `.env` file in the `frontend/` folder:
```env
VITE_API_URL=http://localhost:8000
```

---

## Local Setup & Run

### 1. Database Setup
Ensure PostgreSQL is running locally, create a database named `bytelink`, and run migration revisions:
```bash
cd backend
alembic upgrade head
```

### 2. Backend Setup (Local Virtual Environment)
```bash
cd backend
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```
- API Interactive Swagger docs: `http://localhost:8000/docs`
- Health check status endpoint: `http://localhost:8000/health`

### 3. Frontend Setup (React App)
```bash
cd frontend
npm install
npm run dev
```
- Web dashboard client: `http://localhost:5173`

---

## CI/CD Pipeline & Code Quality Checks

The project includes an automated GitHub Actions pipeline (`.github/workflows/deploy.yml`) which runs on every push and pull request to the `main` branch.

### Upgraded CI Configuration
*   **Checkout & Setups:** Uses modern `actions/checkout@v4`, `actions/setup-python@v5`, and `actions/setup-node@v4`.
*   **Node.js Runtime:** Upgraded to Node.js **22** (resolving deprecation warnings).
*   **Python Runtime:** Configured to run on Python **3.11** for stable module compatibility.

### Local Quality Commands
Before pushing code, verify that formatting, sorting, and linting checks pass:

```bash
# Python Formatting & Lints
black --check backend/
isort --check-only backend/
ruff check backend/

# Frontend Lints & Compilation
cd frontend
npm run lint
npm run build
```

---

## Running Tests
To run unit and integration tests (auth, urls, cache fallback, error handling):
```bash
cd backend
pytest
```

---

## Docker Compose Setup
Boot up the entire network (PostgreSQL database, Redis cache, and Uvicorn API) locally:
```bash
docker-compose up --build
```
This sets up health check validation scripts ensuring services bootstrap in sequential dependency order.

---

## Cloud Deployment

### 1. Render/Railway (Backend & DB/Redis)
- Render deployment is preconfigured in `render.yaml`. Apply the blueprint for instant databases, caching instances, and web services.
- On Railway, configure:
  - Root directory: `backend/`
  - Build command: `pip install -r requirements.txt`
  - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Environment variables mapping database, Redis, secrets, and frontend URL.

### 2. Vercel (Frontend)
- Link the repository, select `frontend` as the Root Directory.
- Inject the environment variable `VITE_API_URL` referencing your deployed API domain.
- Vercel automatically deploys using Vite build scripts and configures routing overrides using `vercel.json`.