import asyncio
import hashlib
import ipaddress
import json
import os
import secrets
import socket
import string
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import httpx
import models
import redis
import security

# Local imports
from database import SessionLocal, engine, get_db
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from firebase_config import initialize_firebase
from loguru import logger
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator
from redis_client import redis_cache
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

# Load environment variables
load_dotenv()

# Active event loop capture for WebSockets broadcast from background tasks
loop = None


async def redis_ws_pubsub_listener():
    """Listens for real-time analytics updates published by worker.py and broadcasts over WebSockets."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url or redis is None:
        return
    try:
        r = redis.from_url(redis_url, decode_responses=True, protocol=2)
        pubsub = r.pubsub()
        pubsub.subscribe("channel:ws:clicks")
        logger.info("Subscribed to channel:ws:clicks for worker analytics broadcasts.")
        while True:
            msg = await asyncio.to_thread(
                pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0
            )
            if msg and msg.get("type") == "message":
                try:
                    payload = json.loads(msg["data"])
                    s_id = payload.get("short_id")
                    stats = payload.get("stats")
                    if s_id and stats:
                        await manager.broadcast(
                            s_id, {"type": "click_update", "data": stats}
                        )
                except Exception as parse_err:
                    logger.warning(f"Error parsing PubSub message: {parse_err}")
            await asyncio.sleep(0.01)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"WebSocket Redis PubSub listener stopped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    logger.info("FastAPI application starting up...")

    # Initialize Firebase Admin SDK
    initialize_firebase()

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
            logger.warning("Redis ping returned False. Running in degraded mode.")
    except Exception as e:
        logger.warning(
            f"Redis connection verification failed: {e}. Running in degraded mode."
        )

    ws_task = asyncio.create_task(redis_ws_pubsub_listener())
    yield
    ws_task.cancel()

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
            "errors": jsonable_encoder(exc.errors()),
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
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
        headers=exc.headers,
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
ENVIRONMENT = os.getenv("ENV", "development").strip().lower()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
if not PUBLIC_BASE_URL and ENVIRONMENT != "production":
    PUBLIC_BASE_URL = os.getenv("BASE_URL")
if not PUBLIC_BASE_URL:
    raise RuntimeError(
        "PUBLIC_BASE_URL environment variable is required in production."
    )
PUBLIC_BASE_URL = PUBLIC_BASE_URL.rstrip("/")
parsed_public_url = urlsplit(PUBLIC_BASE_URL)
if parsed_public_url.scheme not in {"http", "https"} or not parsed_public_url.netloc:
    raise RuntimeError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL.")
if ENVIRONMENT == "production" and parsed_public_url.scheme != "https":
    raise RuntimeError("PUBLIC_BASE_URL must use HTTPS in production.")

# Build the list of allowed origins.
origins = ["https://link-shortener-mauve-pi.vercel.app"]
if ENVIRONMENT != "production":
    origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
    if parsed_public_url.hostname:
        origins.append(f"http://{parsed_public_url.hostname}:5173")
    origins.append(PUBLIC_BASE_URL)

CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "")
for url in CORS_ALLOWED_ORIGINS.split(","):
    trimmed = url.strip().rstrip("/")
    if trimmed and trimmed not in origins:
        origins.append(trimmed)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
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


def get_client_ip(request: Request) -> str:
    """Return the original client address when a trusted proxy supplies it."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request):
    client_ip = get_client_ip(request)
    key = f"rate_limit:{client_ip}"
    limit = int(os.getenv("AUTH_RATE_LIMIT", os.getenv("RATE_LIMIT", "10000")))
    try:
        current = redis_cache.incr(key)
        if current is None:
            return True
        if current == 1:
            redis_cache.expire(key, 60)
        if current > limit:
            logger.warning(f"IP {client_ip} exceeded rate limit.")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Rate limit is {limit} requests per minute.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rate limiting check failed: {e}")
    return True


def get_redirect_status_code() -> int:
    try:
        return int(os.getenv("REDIRECT_STATUS_CODE", "302"))
    except (ValueError, TypeError):
        return 302


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


def track_click(short_id: str, user_agent: str, ip: str, increment_clicks: bool = True):
    # Background tasks run after the request dependency may have been closed.
    with SessionLocal() as db:
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            logger.warning(f"Could not log click for missing short_id: {short_id}")
            return

        if increment_clicks:
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
                manager.broadcast(
                    short_id, {"type": "click_update", "data": stats_data}
                ),
                loop,
            )


# Pydantic schemas
def get_url_blocklist() -> set[str]:
    blocked = set()
    env_blocklist = os.getenv("URL_BLOCKLIST", "")
    for host in env_blocklist.split(","):
        h = host.strip().lower()
        if h:
            blocked.add(h)

    file_path = os.getenv("URL_BLOCKLIST_FILE")
    if file_path and os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    h = line.strip().lower()
                    if h and not h.startswith("#"):
                        blocked.add(h)
        except Exception as e:
            logger.warning(f"Failed to read blocklist file {file_path}: {e}")

    return blocked


def is_ip_private_or_loopback(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except ValueError:
        return False


def validate_target_url_safety(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("target_url must be an absolute HTTP(S) URL")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise ValueError("Invalid target URL: missing hostname")

    # 1. Reject service's own domain
    own_host = (urlsplit(PUBLIC_BASE_URL).hostname or "").strip().lower()
    if own_host and hostname == own_host:
        raise ValueError(
            f"Cannot shorten URLs pointing to ByteLink's own domain ({own_host})"
        )

    # 2. Reject localhost
    if hostname in {"localhost", "localhost.localdomain"}:
        raise ValueError("Cannot shorten URLs pointing to localhost")

    # 3. Reject direct private or loopback IP addresses
    if is_ip_private_or_loopback(hostname):
        raise ValueError(
            "Cannot shorten URLs pointing to private or loopback IP addresses"
        )

    # 4. Check DNS resolution for private IP SSRF prevention
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
        for entry in resolved_ips:
            sockaddr = entry[4]
            ip_candidate = sockaddr[0]
            if is_ip_private_or_loopback(ip_candidate):
                raise ValueError(
                    "Target hostname resolves to a private or loopback IP address"
                )
    except socket.gaierror:
        pass

    # 5. Check against blocklist
    blocklist = get_url_blocklist()
    if hostname in blocklist or any(hostname.endswith("." + b) for b in blocklist):
        raise ValueError(
            f"Target host '{hostname}' is blocked due to abuse or malicious content"
        )

    return value


class URLCreate(BaseModel):
    target_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    password: Optional[str] = None
    max_clicks: Optional[int] = Field(None, ge=1)

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str) -> str:
        return validate_target_url_safety(value)


class URLUpdate(BaseModel):
    target_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    max_clicks: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    clear_password: Optional[bool] = False
    clear_max_clicks: Optional[bool] = False
    clear_expires_at: Optional[bool] = False

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            return validate_target_url_safety(value)
        return value

    @field_validator("max_clicks")
    @classmethod
    def validate_max_clicks(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("max_clicks must be at least 1")
        return value


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Authentication routes
class TokenRefreshRequest(BaseModel):
    refresh_token: str


class APIKeyCreate(BaseModel):
    name: Optional[str] = Field("Default API Key", max_length=100)


@app.post(
    "/api/auth/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit)],
)
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


@app.post("/api/auth/login", dependencies=[Depends(rate_limit)])
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
    current_user: models.User = Depends(security.require_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "firebase_uid": current_user.firebase_uid,
        "created_at": (
            current_user.created_at.isoformat() if current_user.created_at else None
        ),
    }


@app.post("/api/auth/sync")
def sync_user(
    current_user: models.User = Depends(security.require_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "firebase_uid": current_user.firebase_uid,
        "created_at": (
            current_user.created_at.isoformat() if current_user.created_at else None
        ),
    }


# User Links APIs
@app.get("/api/user/links")
def get_user_links(
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
    urls = db.query(models.URL).filter(models.URL.user_id == current_user_id).all()
    return [
        {
            "id": url.id,
            "short_id": url.short_id,
            "target_url": url.target_url,
            "clicks_count": url.clicks_count,
            "created_at": url.created_at,
            "expires_at": url.expires_at,
            "max_clicks": url.max_clicks,
            "is_active": url.is_active,
            "has_password": bool(url.password),
            "short_url": f"{PUBLIC_BASE_URL}/{url.short_id}",
        }
        for url in urls
    ]


@app.patch("/api/user/links/{short_id}")
def update_user_link(
    short_id: str,
    item: URLUpdate,
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    if url.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not own this link",
        )

    if item.target_url is not None:
        url.target_url = item.target_url

    if item.expires_at is not None:
        url.expires_at = item.expires_at
    elif item.clear_expires_at:
        url.expires_at = None

    if item.max_clicks is not None:
        url.max_clicks = item.max_clicks
    elif item.clear_max_clicks:
        url.max_clicks = None

    if item.is_active is not None:
        url.is_active = item.is_active

    if item.clear_password:
        url.password = None
    elif item.password is not None:
        if item.password.strip() == "":
            url.password = None
        else:
            url.password = security.hash_link_password(item.password)

    db.commit()
    db.refresh(url)

    # Invalidate Redis cache
    try:
        redis_cache.delete(f"url:{short_id}", f"url:{short_id}:clicks")
    except Exception as e:
        logger.warning(f"Could not invalidate cache for updated link {short_id}: {e}")

    return {
        "id": url.id,
        "short_id": url.short_id,
        "target_url": url.target_url,
        "clicks_count": url.clicks_count,
        "created_at": url.created_at,
        "expires_at": url.expires_at,
        "max_clicks": url.max_clicks,
        "is_active": url.is_active,
        "has_password": bool(url.password),
        "short_url": f"{PUBLIC_BASE_URL}/{url.short_id}",
    }


@app.delete("/api/user/links/{short_id}")
def delete_user_link(
    short_id: str,
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
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


@app.post("/api/user/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(
    item: APIKeyCreate,
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
    raw_key = f"bl_live_{secrets.token_urlsafe(24)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    prefix = raw_key[:12] + "..."
    key_name = (item.name or "Default API Key").strip()

    new_key = models.APIKey(
        user_id=current_user_id,
        key_hash=key_hash,
        prefix=prefix,
        name=key_name,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    logger.info(f"API key created for user {current_user_id}: {prefix}")

    return {
        "id": new_key.id,
        "name": new_key.name,
        "prefix": new_key.prefix,
        "api_key": raw_key,
        "created_at": new_key.created_at.isoformat() if new_key.created_at else None,
    }


@app.get("/api/user/api-keys")
def list_api_keys(
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
    keys = (
        db.query(models.APIKey)
        .filter(models.APIKey.user_id == current_user_id)
        .order_by(models.APIKey.created_at.desc())
        .all()
    )
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            "is_active": k.revoked_at is None,
        }
        for k in keys
    ]


@app.delete("/api/user/api-keys/{key_id}")
def revoke_api_key(
    key_id: int,
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
    key = (
        db.query(models.APIKey)
        .filter(
            models.APIKey.id == key_id,
            models.APIKey.user_id == current_user_id,
        )
        .first()
    )
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    if key.revoked_at is None:
        key.revoked_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"API key {key_id} revoked by user {current_user_id}")
    return {"message": "API key revoked successfully"}


# URL Shortening endpoint
@app.post("/api/shorten", dependencies=[Depends(rate_limit)])
def create_short_url(
    item: URLCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(security.require_current_user_id),
):
    target_url_str = str(item.target_url)

    # Secure password if provided
    hashed_pwd = security.hash_link_password(item.password) if item.password else None

    if item.custom_alias:
        short_id = item.custom_alias
        new_url = models.URL(
            short_id=short_id,
            target_url=target_url_str,
            expires_at=item.expires_at,
            password=hashed_pwd,
            user_id=current_user_id,
            max_clicks=item.max_clicks,
            is_active=True,
        )
        db.add(new_url)
        try:
            db.commit()
            db.refresh(new_url)
        except IntegrityError:
            db.rollback()
            logger.warning(f"Conflict: Alias '{item.custom_alias}' already in use.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Alias already in use. Please select another alias.",
            )
    else:
        max_retries = 5
        new_url = None
        for attempt in range(max_retries):
            short_id = generate_short_id()
            new_url = models.URL(
                short_id=short_id,
                target_url=target_url_str,
                expires_at=item.expires_at,
                password=hashed_pwd,
                user_id=current_user_id,
                max_clicks=item.max_clicks,
                is_active=True,
            )
            db.add(new_url)
            try:
                db.commit()
                db.refresh(new_url)
                break
            except IntegrityError:
                db.rollback()
                logger.warning(
                    f"Short ID collision on '{short_id}' (attempt {attempt + 1}/{max_retries}). Retrying..."
                )
                if attempt == max_retries - 1:
                    logger.error(
                        "Failed to generate a unique short_id after max retries."
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Could not generate unique short URL. Please try again.",
                    )
    logger.info(
        f"Short link created: {short_id} -> {target_url_str} (User: {current_user_id})"
    )

    cache_data = {
        "target_url": target_url_str,
        "password": bool(hashed_pwd),
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "max_clicks": item.max_clicks,
        "is_active": True,
        "clicks_count": 0,
    }
    try:
        redis_cache.set(f"url:{short_id}", json.dumps(cache_data))
    except Exception as e:
        logger.warning(f"Could not write cache entry for {short_id}: {e}")

    return {
        "short_id": short_id,
        "target_url": target_url_str,
        "short_url": f"{PUBLIC_BASE_URL}/{short_id}",
        "max_clicks": item.max_clicks,
        "is_active": True,
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


# Metrics endpoint
@app.get("/api/metrics")
def get_metrics():
    hits = 0
    misses = 0
    total = 0
    try:
        raw_hits = redis_cache.get("metrics:redirect:cache_hits")
        raw_misses = redis_cache.get("metrics:redirect:cache_misses")
        raw_total = redis_cache.get("metrics:redirect:total")
        hits = int(raw_hits) if raw_hits is not None else 0
        misses = int(raw_misses) if raw_misses is not None else 0
        total = int(raw_total) if raw_total is not None else 0
    except Exception as e:
        logger.warning(f"Failed to read redirect metrics from Redis: {e}")

    effective_total = max(total, hits + misses)
    hit_rate = (hits / effective_total) if effective_total > 0 else 0.0

    return {
        "total_redirects": effective_total,
        "cache_hits": hits,
        "cache_misses": misses,
        "cache_hit_rate": round(hit_rate, 4),
    }


class ReportCreate(BaseModel):
    reason: Optional[str] = "abuse"


@app.post("/api/report/{short_id}", dependencies=[Depends(rate_limit)])
def report_abuse(
    short_id: str,
    request: Request,
    item: Optional[ReportCreate] = None,
    db: Session = Depends(get_db),
):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )

    reporter_ip = get_client_ip(request)
    reason = item.reason if item else "abuse"

    # Distinct report insertion (ignored if already reported by this IP)
    try:
        report = models.LinkReport(
            url_id=url.id,
            reporter_ip=reporter_ip,
            reason=reason,
        )
        db.add(report)
        db.commit()
    except IntegrityError:
        db.rollback()

    distinct_count = (
        db.query(models.LinkReport).filter(models.LinkReport.url_id == url.id).count()
    )

    threshold = int(os.getenv("REPORT_AUTO_DISABLE_THRESHOLD", "5"))
    if distinct_count >= threshold and url.is_active:
        url.is_active = False
        db.commit()
        db.refresh(url)
        try:
            redis_cache.delete(f"url:{short_id}", f"url:{short_id}:clicks")
        except Exception as e:
            logger.warning(
                f"Could not clear cache for auto-disabled link {short_id}: {e}"
            )
        logger.warning(
            f"Link {short_id} automatically disabled after {distinct_count} distinct abuse reports."
        )

    return {
        "status": "reported",
        "short_id": short_id,
        "distinct_reports": distinct_count,
        "is_active": url.is_active,
    }


# Redirection endpoints
@app.get("/{short_id}")
@app.head("/{short_id}")
def redirect_url(
    short_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if short_id in ["api", "favicon.ico"]:
        raise HTTPException(status_code=404)

    # Sliding-window rate limit per client IP
    client_ip = get_client_ip(request)
    redirect_limit = int(os.getenv("REDIRECT_RATE_LIMIT", "10000"))
    redirect_window = int(os.getenv("REDIRECT_RATE_WINDOW", "60"))
    rate_key = f"rate_limit:redirect:{client_ip}"
    allowed, _rem, retry_after = redis_cache.sliding_window_rate_limit(
        rate_key, redirect_window, redirect_limit
    )
    if not allowed:
        logger.warning(f"Redirect rate limit exceeded for client IP {client_ip}.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many redirect requests. Please slow down.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        redis_cache.incr("metrics:redirect:total")
    except Exception as e:
        logger.warning(f"Could not increment total redirects metric: {e}")

    cache_entry = None
    try:
        cache_entry = redis_cache.get(f"url:{short_id}")
    except Exception as e:
        logger.warning(f"Could not read cache: {e}")

    password = False
    expires_at = None
    target_url = None
    max_clicks = None
    is_active = True
    cached_clicks = 0
    increment_clicks = True

    if cache_entry:
        try:
            data = json.loads(cache_entry)
            target_url = data.get("target_url")
            password = data.get("password")
            expires_at = data.get("expires_at")
            if expires_at:
                expires_at = datetime.fromisoformat(expires_at)
            max_clicks = data.get("max_clicks")
            is_active = data.get("is_active", True)
            cached_clicks = data.get("clicks_count", 0)
        except Exception:
            target_url = cache_entry
            max_clicks = None
            is_active = True
            cached_clicks = 0

    if target_url:
        # Check active status on cache path
        if not is_active:
            return HTMLResponse(
                get_html_template(
                    "Link Expired",
                    "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                )
            )

        # Check click limit atomically on cache path
        if max_clicks is not None:
            if request.method == "HEAD":
                current_clicks = redis_cache.get(f"clicks:{short_id}")
                if current_clicks is not None and int(current_clicks) >= max_clicks:
                    return HTMLResponse(
                        get_html_template(
                            "Link Expired",
                            "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                        )
                    )
            else:
                if not redis_cache.check_and_incr_clicks(
                    short_id, max_clicks, initial_count=cached_clicks
                ):
                    return HTMLResponse(
                        get_html_template(
                            "Link Expired",
                            "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                        )
                    )

        try:
            redis_cache.incr("metrics:redirect:cache_hits")
        except Exception as e:
            logger.warning(f"Could not increment cache hits metric: {e}")
    else:
        try:
            redis_cache.incr("metrics:redirect:cache_misses")
        except Exception as e:
            logger.warning(f"Could not increment cache misses metric: {e}")

        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            logger.warning(f"Short URL redirect not found: {short_id}")
            raise HTTPException(status_code=404, detail="URL not found")

        # Check active status on DB path
        if not url.is_active:
            return HTMLResponse(
                get_html_template(
                    "Link Expired",
                    "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                )
            )

        # Check click limit atomically on DB path
        if url.max_clicks is not None:
            if request.method == "HEAD":
                if url.clicks_count >= url.max_clicks:
                    return HTMLResponse(
                        get_html_template(
                            "Link Expired",
                            "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                        )
                    )
                increment_clicks = False
            else:
                res = db.execute(
                    text(
                        "UPDATE urls SET clicks_count = clicks_count + 1 "
                        "WHERE id = :id AND is_active = true AND clicks_count < max_clicks "
                        "RETURNING id"
                    ),
                    {"id": url.id},
                ).fetchone()
                db.commit()
                if not res:
                    return HTMLResponse(
                        get_html_template(
                            "Link Expired",
                            "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                        )
                    )
                increment_clicks = False
        else:
            increment_clicks = True

        target_url = url.target_url
        password = bool(url.password)
        expires_at = url.expires_at

        # Write to Cache for next requests
        cache_data = {
            "target_url": target_url,
            "password": password,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "max_clicks": url.max_clicks,
            "is_active": url.is_active,
            "clicks_count": url.clicks_count,
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

    if request.method != "HEAD":
        user_agent = request.headers.get("user-agent", "Unknown")
        ip = get_client_ip(request)

        stream_pushed = False
        try:
            if redis_cache.client:
                redis_cache.client.xadd(
                    "stream:clicks",
                    {
                        "event_id": uuid.uuid4().hex,
                        "short_id": short_id,
                        "ip": ip,
                        "user_agent": user_agent,
                        "increment_clicks": "1" if increment_clicks else "0",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                stream_pushed = True
        except Exception as e:
            logger.warning(
                f"Could not push to Redis Stream ({e}); falling back to in-process."
            )

        if not stream_pushed:
            background_tasks.add_task(
                track_click, short_id, user_agent, ip, increment_clicks
            )

    return RedirectResponse(url=target_url, status_code=get_redirect_status_code())


@app.post("/{short_id}", dependencies=[Depends(rate_limit)])
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

    if not url.is_active:
        return HTMLResponse(
            get_html_template(
                "Link Expired",
                "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
            )
        )

    increment_clicks = True
    if url.max_clicks is not None:
        res = db.execute(
            text(
                "UPDATE urls SET clicks_count = clicks_count + 1 "
                "WHERE id = :id AND is_active = true AND clicks_count < max_clicks "
                "RETURNING id"
            ),
            {"id": url.id},
        ).fetchone()
        db.commit()
        if not res:
            return HTMLResponse(
                get_html_template(
                    "Link Expired",
                    "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                )
            )
        increment_clicks = False

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
    ip = request.client.host if request.client else "127.0.0.1"

    stream_pushed = False
    try:
        if redis_cache.client:
            redis_cache.client.xadd(
                "stream:clicks",
                {
                    "event_id": uuid.uuid4().hex,
                    "short_id": short_id,
                    "ip": ip,
                    "user_agent": user_agent,
                    "increment_clicks": "1" if increment_clicks else "0",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            stream_pushed = True
    except Exception as e:
        logger.warning(
            f"Could not push to Redis Stream ({e}); falling back to in-process."
        )

    if not stream_pushed:
        background_tasks.add_task(
            track_click, short_id, user_agent, ip, increment_clicks
        )

    return RedirectResponse(url=url.target_url, status_code=303)


# Static API endpoint stats
@app.get("/api/stats/{short_id}")
def get_stats(
    short_id: str,
    current_user_id: int = Depends(security.require_current_user_id),
    db: Session = Depends(get_db),
):
    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url or url.user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Link not found")

    if url.user_id is None:
        raise HTTPException(status_code=404, detail="Analytics not available")
    return compile_stats(url, db)


# Live WebSockets endpoint stats
@app.websocket("/api/ws/stats/{short_id}")
async def websocket_stats(websocket: WebSocket, short_id: str):
    token = websocket.query_params.get("token")
    with SessionLocal() as db:
        user = security.get_current_user_from_token(token, db)
        if user is None:
            await websocket.close(code=1008, reason="Authentication required")
            return
        current_user_id = user.id
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url or url.user_id != current_user_id:
            await websocket.close(code=1008, reason="Link not found or unauthorized")
            return
        initial_stats = compile_stats(url, db)

    await manager.connect(short_id, websocket)
    try:
        await websocket.send_json({"type": "initial_stats", "data": initial_stats})
        # Loop to keep socket active
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(short_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error on {short_id}: {e}")
        manager.disconnect(short_id, websocket)
