import asyncio
import json
import os
import secrets
import string
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import httpx
import models
import security
# Local imports
from database import SessionLocal, engine, get_db
from dotenv import load_dotenv
from fastapi import (BackgroundTasks, Depends, FastAPI, Form, HTTPException,
                     Request, WebSocket, WebSocketDisconnect, status)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from loguru import logger
from pydantic import BaseModel, EmailStr, HttpUrl, ValidationError
from redis_client import redis_cache
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

# Load environment variables
load_dotenv()

# Active event loop capture for WebSockets broadcast from background tasks
loop = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    logger.info("FastAPI application starting up...")

    # Verify Database Connectivity
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connectivity verified successfully.")
    except Exception as e:
        logger.critical(f"Database connection verification failed: {e}")

    # Verify Redis Connectivity
    try:
        if redis_cache.ping():
            logger.info("Redis connectivity verified successfully.")
        else:
            logger.warning(
                "Redis ping returned False. Running in degraded fallback mode."
            )
    except Exception as e:
        logger.warning(
            f"Redis connection verification failed: {e}. Running in degraded fallback mode."
        )

    yield

    logger.info("FastAPI application shutting down...")

    # Close SQLAlchemy connection pool
    try:
        engine.dispose()
        logger.info("SQLAlchemy connection pool disposed.")
    except Exception as e:
        logger.error(f"Error disposing SQLAlchemy connection pool: {e}")

    # Close Redis connection if supported
    try:
        if hasattr(redis_cache, "client") and redis_cache.client:
            redis_cache.client.close()
            logger.info("Redis connection closed.")
    except Exception as e:
        logger.error(f"Error closing Redis client: {e}")


app = FastAPI(title="ByteLink Production URL Shortener API", lifespan=lifespan)


# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"Request: {request.method} {request.url.path} - Status: {response.status_code} - Duration: {process_time:.2f}ms"
    )
    response.headers["X-Response-Time"] = f"{process_time:.2f}ms"
    return response


# Global Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(
        f"Validation error on {request.method} {request.url.path}: {exc.errors()}"
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": "Validation failed",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    logger.error(f"Pydantic Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "error",
            "message": "Validation failed",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(
        f"HTTP exception on {request.method} {request.url.path}: {exc.status_code} - {exc.detail}"
    )
    return JSONResponse(
        status_code=exc.status_code, content={"status": "error", "message": exc.detail}
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    logger.error(
        f"Database integrity error on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "status": "error",
            "message": "Database conflict: Integrity constraint violated.",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception(
        f"SQLAlchemy query error on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "A database error occurred while processing your request.",
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )


# Configure CORS Origins
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
# Support multi-origin comma-separated values, and always allow localhost in dev
origins = [origin.strip() for origin in frontend_url.split(",") if origin.strip()]
if "http://localhost:5173" not in origins:
    origins.append("http://localhost:5173")
if "http://127.0.0.1:5173" not in origins:
    origins.append("http://127.0.0.1:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health Check Route
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_ok = False
    redis_ok = False

    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Health check database error: {e}")

    try:
        redis_ok = redis_cache.ping()
    except Exception as e:
        logger.error(f"Health check Redis error: {e}")

    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable",
        )

    return {"status": "healthy", "redis": "connected" if redis_ok else "degraded"}


# API Root Landing Schema & Route
class RootResponse(BaseModel):
    message: str
    status: str
    docs: str
    redoc: str
    health: str
    version: str


@app.get("/", response_model=RootResponse, status_code=status.HTTP_200_OK)
async def root():
    return {
        "message": "ByteLink API is running successfully",
        "status": "healthy",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "version": "1.0.0",
    }


# Connection manager for real-time WebSocket analytics
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, short_id: str, websocket: WebSocket):
        await websocket.accept()
        if short_id not in self.active_connections:
            self.active_connections[short_id] = []
        self.active_connections[short_id].append(websocket)
        logger.info(f"WebSocket client connected to short_id: {short_id}")

    def disconnect(self, short_id: str, websocket: WebSocket):
        if short_id in self.active_connections:
            if websocket in self.active_connections[short_id]:
                self.active_connections[short_id].remove(websocket)
            if not self.active_connections[short_id]:
                del self.active_connections[short_id]
        logger.info(f"WebSocket client disconnected from short_id: {short_id}")

    async def broadcast(self, short_id: str, message: dict):
        if short_id in self.active_connections:
            for connection in self.active_connections[short_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Error sending message to WebSocket client: {e}")


manager = ConnectionManager()


def rate_limit(request: Request):
    client_ip = request.client.host
    key = f"rate_limit:{client_ip}"
    try:
        current = redis_cache.incr(key)
        if current == 1:
            redis_cache.expire(key, 60)
        if current > 20:
            logger.warning(f"IP {client_ip} exceeded rate limit.")
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Rate limit is 20 requests per minute.",
            )
    except Exception as e:
        logger.warning(f"Rate limiting check failed: {e}")
    return True


def generate_short_id(length: int = 7) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def compile_stats(url: models.URL, db: Session) -> dict:
    clicks = (
        db.query(models.ClickEvent).filter(models.ClickEvent.url_id == url.id).all()
    )
    countries = {}
    last_clicks = []

    for c in clicks:
        if c.country:
            countries[c.country] = countries.get(c.country, 0) + 1

    for c in clicks[-20:]:
        last_clicks.append(
            {
                "time": c.clicked_at.isoformat() if c.clicked_at else None,
                "country": c.country,
                "city": c.city,
                "ip": c.ip_address,
                "user_agent": c.user_agent,
            }
        )

    return {
        "short_id": url.short_id,
        "target_url": url.target_url,
        "total_clicks": url.clicks_count,
        "countries": countries,
        "recent_clicks": last_clicks,
    }


def track_click(short_id: str, db: Session, user_agent: str, ip: str):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        return

    url.clicks_count += 1

    country, city, lat, lon = None, None, None, None
    if ip and ip != "127.0.0.1" and ip != "localhost":
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"http://ip-api.com/json/{ip}").json()
            if res.get("status") == "success":
                country = res.get("country")
                city = res.get("city")
                lat = res.get("lat")
                lon = res.get("lon")
        except Exception as e:
            logger.error(f"IP lookup failed for {ip}: {e}")

    click = models.ClickEvent(
        url_id=url.id,
        ip_address=ip,
        country=country,
        city=city,
        lat=lat,
        lon=lon,
        user_agent=user_agent,
    )
    try:
        db.add(click)
        db.commit()
        logger.info(
            f"Click logged for short_id: {short_id}. Total clicks: {url.clicks_count}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log click for short_id {short_id}: {e}")
        return

    # Broadcast real-time update to active WebSockets listeners
    stats_data = compile_stats(url, db)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(short_id, {"type": "click_update", "data": stats_data}),
            loop,
        )


# Pydantic schemas
class URLCreate(BaseModel):
    target_url: HttpUrl
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    password: Optional[str] = None


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    email: EmailStr
    google_id: str


# Authentication routes
class TokenRefreshRequest(BaseModel):
    refresh_token: str


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(item: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == item.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    hashed_pwd = security.get_password_hash(item.password)
    user = models.User(email=item.email, hashed_password=hashed_pwd)
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = security.create_access_token(data={"sub": str(user.id)})
    refresh_token = security.create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/api/auth/login")
def login_user(item: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == item.email).first()
    if (
        not user
        or not user.hashed_password
        or not security.verify_password(item.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = security.create_access_token(data={"sub": str(user.id)})
    refresh_token = security.create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/api/auth/google")
def google_auth(item: GoogleAuthRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.google_id == item.google_id).first()
    if not user:
        user = db.query(models.User).filter(models.User.email == item.email).first()
        if user:
            user.google_id = item.google_id
            db.commit()
        else:
            user = models.User(email=item.email, google_id=item.google_id)
            db.add(user)
            db.commit()
            db.refresh(user)

    access_token = security.create_access_token(data={"sub": str(user.id)})
    refresh_token = security.create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/api/auth/refresh")
def refresh_token(item: TokenRefreshRequest, db: Session = Depends(get_db)):
    payload = security.decode_refresh_token(item.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    new_access = security.create_access_token(data={"sub": str(user.id)})
    new_refresh = security.create_refresh_token(data={"sub": str(user.id)})
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@app.get("/api/auth/me")
def get_user_me(
    current_user_id: Optional[int] = Depends(security.get_current_user_id),
    db: Session = Depends(get_db),
):
    if not current_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return {"id": user.id, "email": user.email}


# User Links APIs
@app.get("/api/user/links")
def get_user_links(
    current_user_id: Optional[int] = Depends(security.get_current_user_id),
    db: Session = Depends(get_db),
):
    if not current_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    urls = db.query(models.URL).filter(models.URL.user_id == current_user_id).all()
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return [
        {
            "id": url.id,
            "short_id": url.short_id,
            "target_url": url.target_url,
            "clicks_count": url.clicks_count,
            "created_at": url.created_at,
            "expires_at": url.expires_at,
            "short_url": f"{base_url}/{url.short_id}",
        }
        for url in urls
    ]


@app.delete("/api/user/links/{short_id}")
def delete_user_link(
    short_id: str,
    current_user_id: Optional[int] = Depends(security.get_current_user_id),
    db: Session = Depends(get_db),
):
    if not current_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    url = (
        db.query(models.URL)
        .filter(models.URL.short_id == short_id, models.URL.user_id == current_user_id)
        .first()
    )
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found or unauthorized",
        )

    db.delete(url)
    db.commit()

    # Remove from cache
    try:
        redis_cache.set(f"url:{short_id}", "", ex=1)
    except Exception as e:
        logger.warning(f"Could not clear cache for deleted url {short_id}: {e}")

    return {"detail": "Short URL deleted successfully"}


# URL Shortening endpoint
@app.post("/api/shorten", dependencies=[Depends(rate_limit)])
def create_short_url(
    item: URLCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user_id: Optional[int] = Depends(security.get_current_user_id),
):
    target_url_str = str(item.target_url)

    if item.custom_alias:
        existing = (
            db.query(models.URL)
            .filter(models.URL.short_id == item.custom_alias)
            .first()
        )
        if existing:
            logger.warning(f"Conflict: Alias '{item.custom_alias}' already in use.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Alias already in use. Please select another alias.",
            )
        short_id = item.custom_alias
    else:
        short_id = generate_short_id()
        while db.query(models.URL).filter(models.URL.short_id == short_id).first():
            short_id = generate_short_id()

    # Secure password if provided
    hashed_pwd = security.hash_link_password(item.password) if item.password else None

    new_url = models.URL(
        short_id=short_id,
        target_url=target_url_str,
        expires_at=item.expires_at,
        password=hashed_pwd,
        user_id=current_user_id,
    )
    db.add(new_url)
    db.commit()
    db.refresh(new_url)
    logger.info(
        f"Short link created: {short_id} -> {target_url_str} (User: {current_user_id})"
    )

    cache_data = {
        "target_url": target_url_str,
        "password": bool(hashed_pwd),
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
    }
    try:
        redis_cache.set(f"url:{short_id}", json.dumps(cache_data))
    except Exception as e:
        logger.warning(f"Could not write cache entry for {short_id}: {e}")

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return {
        "short_id": short_id,
        "target_url": target_url_str,
        "short_url": f"{base_url}/{short_id}",
    }


def get_html_template(title, body_content):
    return f"""
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{ background-color: #0f172a; color: #f1f5f9; font-family: system-ui, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
            .card {{ background: rgba(255, 255, 255, 0.05); padding: 2.5rem; border-radius: 1rem; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); text-align: center; max-width: 400px; width: 100%; box-sizing: border-box; }}
            input {{ width: 100%; padding: 0.75rem; margin-top: 1rem; border-radius: 0.5rem; border: 1px solid rgba(255,255,255,0.2); background: rgba(0,0,0,0.2); color: white; box-sizing: border-box; outline: none; }}
            input:focus {{ border-color: #6366f1; }}
            button {{ width: 100%; padding: 0.75rem; margin-top: 1rem; border-radius: 0.5rem; border: none; background: #6366f1; color: white; font-weight: bold; cursor: pointer; transition: 0.2s; }}
            button:hover {{ background: #4f46e5; }}
            .error {{ color: #ef4444; margin-top: 1rem; font-size: 0.9rem; }}
        </style>
    </head>
    <body>
        <div class="card">
            {body_content}
        </div>
    </body>
    </html>
    """


# Redirection endpoints
@app.get("/{short_id}")
def redirect_url(
    short_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if short_id in ["api", "favicon.ico"]:
        raise HTTPException(status_code=404)

    cache_entry = None
    try:
        cache_entry = redis_cache.get(f"url:{short_id}")
    except Exception as e:
        logger.warning(f"Could not read cache: {e}")

    password = False
    expires_at = None
    target_url = None

    if cache_entry:
        try:
            data = json.loads(cache_entry)
            target_url = data.get("target_url")
            password = data.get("password")
            expires_at = data.get("expires_at")
            if expires_at:
                expires_at = datetime.fromisoformat(expires_at)
        except Exception:
            target_url = cache_entry

    if not cache_entry or not target_url:
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            logger.warning(f"Short URL redirect not found: {short_id}")
            raise HTTPException(status_code=404, detail="URL not found")
        target_url = url.target_url
        password = bool(url.password)
        expires_at = url.expires_at

        # Write to Cache for next requests
        cache_data = {
            "target_url": target_url,
            "password": password,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        try:
            redis_cache.set(f"url:{short_id}", json.dumps(cache_data))
        except Exception as e:
            logger.warning(f"Could not update cache: {e}")

    # Expiry verification
    if expires_at and datetime.now(timezone.utc) > expires_at.replace(
        tzinfo=timezone.utc
    ):
        logger.info(f"Access attempt to expired link: {short_id}")
        return HTMLResponse(
            get_html_template(
                "Link Expired",
                "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
            )
        )

    # Render unlock page if password is set
    if password:
        form = f"""
            <h2>Unlock Link</h2>
            <p style="color: #94a3b8; font-size: 0.9em; margin-bottom: 1.5rem;">This link is password protected.</p>
            <form method="post" action="/{short_id}">
                <input type="password" name="password" placeholder="Enter password" required />
                <button type="submit">Unlock</button>
            </form>
        """
        return HTMLResponse(get_html_template("Password Required", form))

    user_agent = request.headers.get("user-agent", "Unknown")
    ip = request.client.host
    background_tasks.add_task(track_click, short_id, db, user_agent, ip)

    return RedirectResponse(url=target_url)


@app.post("/{short_id}")
def verify_password_and_redirect(
    short_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    password: str = Form(...),
):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    # Expiry verification
    if url.expires_at and datetime.now(timezone.utc) > url.expires_at.replace(
        tzinfo=timezone.utc
    ):
        return HTMLResponse(
            get_html_template(
                "Link Expired",
                "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
            )
        )

    # Password check
    if url.password and not security.verify_link_password(password, url.password):
        form = f"""
            <h2>Unlock Link</h2>
            <p style="color: #94a3b8; font-size: 0.9em; margin-bottom: 1.5rem;">This link is password protected.</p>
            <form method="post" action="/{short_id}">
                <input type="password" name="password" placeholder="Enter password" required />
                <button type="submit">Unlock</button>
                <div class="error">Incorrect password. Please try again.</div>
            </form>
        """
        return HTMLResponse(get_html_template("Password Required", form))

    user_agent = request.headers.get("user-agent", "Unknown")
    ip = request.client.host
    background_tasks.add_task(track_click, short_id, db, user_agent, ip)

    return RedirectResponse(url=url.target_url, status_code=303)


# Static API endpoint stats
@app.get("/api/stats/{short_id}")
def get_stats(short_id: str, db: Session = Depends(get_db)):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    return compile_stats(url, db)


# Live WebSockets endpoint stats
@app.websocket("/api/ws/stats/{short_id}")
async def websocket_stats(websocket: WebSocket, short_id: str):
    await manager.connect(short_id, websocket)
    try:
        # Send initial data compilation
        with SessionLocal() as db:
            url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
            if url:
                initial_stats = compile_stats(url, db)
                await websocket.send_json(
                    {"type": "initial_stats", "data": initial_stats}
                )

        # Loop to keep socket active
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(short_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error on {short_id}: {e}")
        manager.disconnect(short_id, websocket)
