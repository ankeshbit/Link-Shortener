# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener application built with modern web technologies. It provides instantaneous link redirections, custom alias creations, password lock protections, user authentication dashboards, and real-time geographical analytics streaming via WebSockets.

---

## Features
- **User Accounts & JWT Auth:** Secure registration, token-based login, automatic access token refreshing, and Google OAuth compatibility.
- **Asymmetrical Live Analytics Dashboard:** Track click frequencies, top countries, and real-time logs.
- **WebSocket-Based Updates:** Stats update dynamically on the screen as clicks happen.
- **Advanced Shortening Options:** Custom short path aliases, link expiration date timers, and sha256-encrypted password protection.
- **QR Code Generator:** Scan short links instantly using built-in canvas graphics.
- **Caching & Rate Limiting:** High-speed cached reads and client rate limits powered by Redis.
- **Database Migrations:** SQL schema managed by Alembic, ensuring PostgreSQL is utilized everywhere.
- **Fault-Tolerant Cache:** Resilient runtime wrapper allowing graceful fallback to local memory caching if Redis goes offline.

---

## Tech Stack
*   **Frontend:** React 19 (Vite, Axios, Chart.js, Lucide-React, Framer Motion)
*   **Backend:** FastAPI (Python 3.11, Uvicorn, WebSockets, Background Tasks)
*   **Database:** PostgreSQL (production & local), Alembic Migrations, SQLAlchemy ORM
*   **Caching & Limit Store:** Redis Cache (with SafeRedisClient fallback)
*   **Containerization:** Docker & Docker Compose
*   **Hosting Runtimes:** Railway / Render (Backend/DB/Redis), Vercel (Frontend SPA)
*   **CI/CD:** GitHub Actions Pipelines (linting, tests, build checks, and Docker builds)

---

## Folder Structure
```text
Link-Shortener/
├── .github/workflows/
│   └── deploy.yml          # CI/CD workflow pipeline
├── backend/
│   ├── alembic/            # Database schema migration versions
│   ├── alembic.ini         # Alembic configuration
│   ├── main.py             # FastAPI entrypoint, middlewares, routers & exceptions
│   ├── database.py         # SQLAlchemy engine connection & Session dependency
│   ├── models.py           # SQL DB Schema models (Postgres)
│   ├── security.py         # JWT tokens & bcrypt password hashing
│   ├── redis_client.py     # Resilient Redis engine wrapper
│   ├── test_main.py        # PyTest automated unit tests
│   ├── requirements.txt    # Python dependencies list
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
│   │   │   ├── SignIn.jsx              # Auth credentials register/login card
│   │   │   └── ... UI Decorators
│   │   ├── App.jsx         # App router maps & Navigation
│   │   └── index.css       # Custom HSL CSS variables & animations
│   ├── vercel.json         # SPA router redirect rule
│   └── package.json        # Frontend dependencies list
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
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=super-secret-dev-key-for-bytelink-url-shortener-123456
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