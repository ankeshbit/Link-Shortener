# ByteLink — Premium Full-Stack URL Shortener & Live Analytics

ByteLink is a production-grade, full-stack URL Shortener application built with modern web technologies: React 19, Vite, FastAPI, PostgreSQL, Redis, and Firebase Authentication. It provides instantaneous link redirections, custom alias creations, password lock protections, user authentication dashboards, and real-time geographical analytics streaming via WebSockets.

---

## Localhost-Only Development Setup (Windows PowerShell)

Follow this complete step-by-step guide to run ByteLink 100% locally on Windows using PowerShell.

### 1. Prerequisites
Ensure the following tools are installed on your Windows machine:
- **Python 3.10+** (verify with `python --version`)
- **Node.js 18+ & npm** (verify with `node -v` and `npm -v`)
- **Docker Desktop** (for local PostgreSQL and Redis containers, or running native PostgreSQL and Redis services)
- **Git** (verify with `git --version`)

### 2. Environment File Setup
Clone the repository and copy the environment configuration templates:

```powershell
# Navigate to repository root
cd C:\path\to\Link-Shortener

# Copy backend environment template
Copy-Item backend\.env.example backend\.env

# Copy frontend environment template
Copy-Item frontend\.env.example frontend\.env
```

Ensure `.env` files contain your local configuration:
- In `backend\.env`:
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
  *(Note: `JWT_SECRET` must be at least 32 characters long. The backend fails fast at startup if it is missing or too short).*
- In `frontend\.env`:
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

### 3. Firebase Service-Account Setup (Optional & Dual-Mode)
ByteLink supports dual-mode Firebase ID token verification:
1. **Zero-Configuration Mode (Default):** The backend cryptographically validates tokens directly against Google's public x509 certificates matching `FIREBASE_PROJECT_ID`. No service account key is needed for local development!
2. **Service Account Key Mode (Optional):** If you prefer Firebase Admin SDK initialization with service credentials:
   - In the Firebase Console, go to **Project Settings → Service accounts → Generate new private key**.
   - Copy the private key and client email into `backend\.env`:
     ```ini
     FIREBASE_CLIENT_EMAIL=firebase-adminsdk-xxxxx@link-shortener-6c96e.iam.gserviceaccount.com
     FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
     ```
   - Escaped `\n` characters are automatically parsed and normalized.

### 4. Starting PostgreSQL and Redis
Launch local PostgreSQL (port 5432) and Redis (port 6379) via Docker Compose:

```powershell
docker compose up -d postgres redis
```
Verify the containers are healthy:
```powershell
docker compose ps
```

### 5. Creating and Activating Python Virtual Environment
In the repository root:

```powershell
# Create virtual environment inside backend
python -m venv backend\.venv

# Activate virtual environment
.\backend\.venv\Scripts\Activate.ps1
```
*(If PowerShell execution policies prevent script activation, run: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`)*

### 6. Installing Backend Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

### 7. Running Database Migrations
Apply Alembic migrations to create the database schema:

```powershell
python -m alembic -c backend\alembic.ini upgrade head
```

### 8. Starting FastAPI Backend
Launch the FastAPI development server:

```powershell
python -m uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```
Verify:
- API Root: `http://localhost:8000/`
- API Health Check: `http://localhost:8000/health`
- Swagger UI Documentation: `http://localhost:8000/docs`

### 9. Installing Frontend Dependencies
Open a second PowerShell window:

```powershell
cd frontend
npm install
```

### 10. Starting Vite Frontend
Start the Vite development server:

```powershell
npm run dev
```
Open `http://localhost:5173` in your browser.

### 11. Testing Google Authentication
1. On `http://localhost:5173`, click **Sign In with Google**.
2. Complete the Google popup authentication.
3. The app receives a Firebase ID token, stores it locally, and automatically calls `POST /api/auth/sync` on the local backend to synchronize your account in PostgreSQL.
4. Your user profile will appear in the top navigation bar.

### 12. Testing URL Creation
1. In the hero input, enter any destination URL (e.g., `https://example.com/docs`).
2. Optionally expand **Advanced Options** to enter a custom alias (e.g., `my-docs`), expiration date, or password lock.
3. Click **Shorten URL**.
4. The local backend stores the link in PostgreSQL, caches it in Redis, and returns `http://localhost:8000/<short_id>`.

### 13. Testing Short URL Redirection
1. Copy the generated short URL (e.g., `http://localhost:8000/my-docs`).
2. Open a new browser tab or an Incognito window and paste the short link.
3. The local backend resolves the link from Redis/PostgreSQL, records click metadata asynchronously, and immediately issues an HTTP 307 redirect to `https://example.com/docs`.
4. Open the **Analytics Dashboard** on `http://localhost:5173/dashboard` to verify real-time click metrics and geolocation logs.

### 14. Troubleshooting Common Errors
- **Error: "Script execution is disabled on this system" in PowerShell:**
  Run: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
- **Error: "Path doesn't exist: alembic":**
  Use the `-c` flag pointing to `backend\alembic.ini`:
  `python -m alembic -c backend\alembic.ini upgrade head`
- **Error: "Connection refused to localhost:5432":**
  Ensure Docker Desktop is running and run `docker compose up -d postgres redis`.
- **Error: "CORS error on API requests":**
  Verify that `CORS_ALLOWED_ORIGINS` in `backend\.env` contains `http://localhost:5173,http://127.0.0.1:5173` and `VITE_API_URL` in `frontend\.env` is `http://localhost:8000`.
- **Automated Startup Script:**
  You can run all backend and frontend services with a single PowerShell script:
  ```powershell
  .\start-local.ps1
  ```

---

## Features

| Feature | Description |
|---|---|
| **User Accounts & Firebase Auth** | Secure Google login, Bearer token authorization, automatic token refreshing |
| **Live Analytics Dashboard** | Track clicks, top countries, devices, and real-time logs via WebSockets |
| **Advanced Shortening Options** | Custom aliases, link expiry timers, bcrypt-encrypted password protection |
| **QR Code Generator** | Built-in canvas-rendered QR codes with PNG download |
| **Caching & Rate Limiting** | High-speed Redis-backed caching with graceful fallback when Redis is restarting |
| **Explicit CORS Configuration** | Localhost origins enabled in development, explicit origin whitelist in production |
| **Professional API Landing** | Async `/` route returning health and endpoint metadata instead of a 404 |
| **Robust Validation Errors** | Human-readable validation messages with detailed diagnostic logging |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite, Axios, Chart.js, Lucide Icons, Framer Motion |
| **Backend** | FastAPI 0.137+, Python 3.10/3.11, Uvicorn, WebSockets, Background Tasks |
| **Database** | PostgreSQL, SQLAlchemy 2.0 ORM, Alembic Migrations |
| **Cache / Rate Limit** | Redis (local or cloud), SafeRedisClient fallback |
| **Authentication** | Firebase Authentication (Google OAuth + RS256 JWTs) |
| **Containerization** | Docker, Docker Compose |
| **Testing** | Pytest, TestClient, AnyIO |

---

## Folder Structure

```text
Link-Shortener/
├── backend/
│   ├── alembic/                # Database schema migration versions
│   ├── alembic.ini             # Alembic configuration
│   ├── main.py                 # FastAPI app — routes, middleware, CORS, error handlers
│   ├── database.py             # SQLAlchemy engine & Session dependency
│   ├── models.py               # ORM models for PostgreSQL
│   ├── security.py             # Auth verification, Bearer extraction, bcrypt hashing
│   ├── firebase_config.py      # Dual-mode Firebase token verification & cert cache
│   ├── redis_client.py         # SafeRedisClient with graceful fallback
│   ├── test_main.py            # Pytest test suite (32 tests)
│   ├── requirements.txt        # Python dependency stack
│   ├── Dockerfile              # Slim Python 3.11 Docker image
│   └── .env.example            # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── axios.js        # Axios instance with Firebase ID token attach & 401 refresh
│   │   ├── auth/
│   │   │   ├── firebase.js     # Firebase client SDK initialization & Google OAuth
│   │   │   └── AuthContext.jsx # React AuthContext provider
│   │   ├── components/
│   │   │   ├── ShortenerForm.jsx       # Shortener form, error handler, live preview
│   │   │   ├── AnalyticsDashboard.jsx  # Click charts, geo logs, WebSocket live updates
│   │   │   ├── Dashboard.jsx           # User links history management
│   │   │   ├── SignIn.jsx              # Google sign-in modal/page
│   │   │   └── ErrorBoundary.jsx       # React error boundary
│   │   ├── App.jsx             # Route declarations & navigation bar
│   │   └── index.css           # Design system & styles
│   ├── package.json            # Frontend dependencies
│   └── .env.example            # Frontend environment template
├── docker-compose.yml          # Local PostgreSQL & Redis orchestration
├── start-local.ps1             # One-click Windows PowerShell startup script
├── start-local.bat             # One-click Windows batch startup script
├── start-local.sh              # One-click Linux/macOS bash startup script
└── README.md
```

---

## Running Automated Tests

Run the full automated test suite (32 tests):

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\test_main.py -v
```

Tests cover:
- Health check and root endpoints
- Firebase token authentication and user creation
- Invalid, expired, and missing Firebase tokens (HTTP 401)
- Authenticated URL shortening
- Custom alias conflicts (HTTP 409)
- Target URL validation (HTTP 422)
- PostgreSQL insertion failure handling (HTTP 500)
- Redis cache unavailability resilience
- Public short URL redirection (HTTP 307)
- Password-protected short link verification
- Expiration handling (HTTP 410 / expired message)
- Cross-origin CORS preflight headers for localhost
- Cross-session database persistence verification
- Public certificate cryptographic signature validation
