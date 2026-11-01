import asyncio
import html
import ipaddress
import json
import os
import re
import secrets
import string
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import httpx
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from loguru import logger
from pydantic import BaseModel, EmailStr, ValidationError, field_validator
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
import security
from database import SessionLocal, engine, get_db
from firebase_config import initialize_firebase
from redis_client import redis_cache

try:
    from user_agents import parse as parse_user_agent
except ImportError:
    parse_user_agent = None

# Load environment variables
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Active event loop capture for WebSockets broadcast from background tasks
loop = None


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
    raw_errors = jsonable_encoder(exc.errors())
    first_msg = (
        raw_errors[0].get("msg", "Validation failed")
        if raw_errors
        else "Validation failed"
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": first_msg,
            "detail": raw_errors,
            "errors": raw_errors,
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    logger.error(f"Pydantic Validation error: {exc.errors()}")
    raw_errors = jsonable_encoder(exc.errors())
    first_msg = (
        raw_errors[0].get("msg", "Validation failed")
        if raw_errors
        else "Validation failed"
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "error",
            "message": first_msg,
            "detail": raw_errors,
            "errors": raw_errors,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.error(
        f"HTTP exception on {request.method} {request.url.path}: {exc.status_code} - {exc.detail}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": str(exc.detail),
            "detail": exc.detail,
        },
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    logger.error(
        f"Database integrity error on {request.method} {request.url.path}: {exc}"
    )
    msg = (
        "Alias already in use. Please select another alias."
        if "short_id" in str(exc).lower()
        else "Database conflict: Integrity constraint violated."
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "status": "error",
            "message": msg,
            "detail": msg,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception(
        f"SQLAlchemy query error on {request.method} {request.url.path}: {exc}"
    )
    msg = "A database error occurred while processing your request."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": msg,
            "detail": msg,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}"
    )
    msg = "An unexpected error occurred. Please try again later."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": msg,
            "detail": msg,
        },
    )


# Environment and Public URL Configuration
ENVIRONMENT = os.getenv("ENV", "development").strip().lower()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
if not PUBLIC_BASE_URL and ENVIRONMENT != "production":
    PUBLIC_BASE_URL = os.getenv("BASE_URL")
if not PUBLIC_BASE_URL:
    if ENVIRONMENT == "production":
        raise RuntimeError(
            "PUBLIC_BASE_URL environment variable is required in production."
        )
    PUBLIC_BASE_URL = "http://localhost:8000"
PUBLIC_BASE_URL = PUBLIC_BASE_URL.rstrip("/")
parsed_public_url = urlsplit(PUBLIC_BASE_URL)
if parsed_public_url.scheme not in {"http", "https"} or not parsed_public_url.netloc:
    raise RuntimeError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL.")
if ENVIRONMENT == "production" and parsed_public_url.scheme != "https":
    raise RuntimeError("PUBLIC_BASE_URL must use HTTPS in production.")

# Build allowed CORS origins strictly from configuration
origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if parsed_public_url.hostname and parsed_public_url.hostname not in {
    "localhost",
    "127.0.0.1",
}:
    origins.append(f"{parsed_public_url.scheme}://{parsed_public_url.netloc}")
if PUBLIC_BASE_URL not in origins:
    origins.append(PUBLIC_BASE_URL)

CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "")
for url in CORS_ALLOWED_ORIGINS.split(","):
    trimmed = url.strip().rstrip("/")
    if trimmed and trimmed not in origins:
        origins.append(trimmed)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reverse proxy and legacy auth flags
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))
ENABLE_LEGACY_AUTH = os.getenv("ENABLE_LEGACY_AUTH", "false").strip().lower() in (
    "true",
    "1",
    "yes",
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
    """Return the client IP, respecting TRUSTED_PROXY_COUNT for reverse proxies."""
    remote_ip = request.client.host if request.client else "127.0.0.1"

    if TRUSTED_PROXY_COUNT > 0:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
            if len(ips) >= TRUSTED_PROXY_COUNT:
                candidate_ip = ips[-TRUSTED_PROXY_COUNT]
                try:
                    ipaddress.ip_address(candidate_ip)
                    return candidate_ip
                except ValueError:
                    logger.warning(
                        f"Invalid IP address in X-Forwarded-For: {candidate_ip}"
                    )

    try:
        ipaddress.ip_address(remote_ip)
        return remote_ip
    except ValueError:
        return "127.0.0.1"


def is_public_ip(ip_str: str) -> bool:
    """Return True if IP address is a valid public, routable IP address."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_link_local
        )
    except ValueError:
        return False


def check_rate_limit(key: str, limit: int = 20, window: int = 60):
    """
    Atomic rate limiting with Redis Lua script.
    Re-raises HTTPException on limit exceeded.
    Fails open only for infrastructure/connection errors.
    """
    try:
        current = redis_cache.atomic_incr_expire(key, expire=window)
        if current is not None and current > limit:
            logger.warning(f"Rate limit exceeded for {key} ({current}/{limit})")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Rate limit is {limit} requests per minute.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Rate limiting infrastructure error: {e}")
        return True
    return True


def rate_limit(request: Request):
    client_ip = get_client_ip(request)
    key = f"rate_limit:{client_ip}"
    return check_rate_limit(key, limit=20, window=60)


def generate_short_id(length: int = 7) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def compile_stats(url: models.URL, db: Session) -> dict:
    """Compile click statistics using SQL GROUP BY aggregation and limited recent history."""
    # 1. SQL GROUP BY for countries aggregation
    country_counts = (
        db.query(models.ClickEvent.country, func.count(models.ClickEvent.id))
        .filter(
            models.ClickEvent.url_id == url.id,
            models.ClickEvent.country.isnot(None),
        )
        .group_by(models.ClickEvent.country)
        .all()
    )
    countries = {c: count for c, count in country_counts if c}

    # 2. Last 20 clicks ordered by clicked_at DESC, id DESC
    recent_events = (
        db.query(models.ClickEvent)
        .filter(models.ClickEvent.url_id == url.id)
        .order_by(models.ClickEvent.clicked_at.desc(), models.ClickEvent.id.desc())
        .limit(20)
        .all()
    )
    last_clicks = [
        {
            "time": c.clicked_at.isoformat() if c.clicked_at else None,
            "country": c.country,
            "city": c.city,
            "ip": c.ip_address,
            "user_agent": c.user_agent,
            "browser": c.browser,
            "os": c.os,
            "device": c.device,
        }
        for c in reversed(recent_events)
    ]

    return {
        "short_id": url.short_id,
        "target_url": url.target_url,
        "total_clicks": url.clicks_count,
        "countries": countries,
        "recent_clicks": last_clicks,
    }


def track_click(short_id: str, user_agent: str, ip: str):
    """Background task to record click event and broadcast live updates."""
    with SessionLocal() as db:
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url:
            logger.warning(f"Could not log click for missing short_id: {short_id}")
            return

        # Atomically increment clicks_count in the database
        db.query(models.URL).filter(models.URL.id == url.id).update(
            {models.URL.clicks_count: models.URL.clicks_count + 1},
            synchronize_session="fetch",
        )

        country, city, lat, lon = None, None, None, None
        if ip and is_public_ip(ip):
            try:
                # Use HTTPS for GeoIP lookups, and only query for public addresses
                with httpx.Client(timeout=2.0) as client:
                    res = client.get(f"https://ipapi.co/{ip}/json/").json()
                    if res.get("country_name"):
                        country = res.get("country_name")
                        city = res.get("city")
                        lat = res.get("latitude")
                        lon = res.get("longitude")
            except Exception as e:
                logger.debug(f"GeoIP lookup failed for {ip}: {e}")

        browser, os_name, device = None, None, None
        if user_agent and user_agent != "Unknown" and parse_user_agent:
            try:
                ua = parse_user_agent(user_agent)
                browser = ua.browser.family or None
                os_name = ua.os.family or None
                if ua.is_mobile:
                    device = "Mobile"
                elif ua.is_tablet:
                    device = "Tablet"
                elif ua.is_pc:
                    device = "Desktop"
                elif ua.is_bot:
                    device = "Bot"
                else:
                    device = "Other"
            except Exception as e:
                logger.debug(f"User agent parsing failed: {e}")

        click = models.ClickEvent(
            url_id=url.id,
            ip_address=ip,
            country=country,
            city=city,
            lat=lat,
            lon=lon,
            user_agent=user_agent,
            browser=browser,
            os=os_name,
            device=device,
        )
        try:
            db.add(click)
            db.commit()
            db.refresh(url)
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
ALIAS_REGEX = re.compile(r"^[A-Za-z0-9_-]{3,50}$")
RESERVED_ALIASES = {
    "api",
    "docs",
    "redoc",
    "openapi.json",
    "health",
    "favicon.ico",
    "ws",
    "stats",
    "user",
    "auth",
    "shorten",
    "dashboard",
    "login",
    "register",
    "static",
    "null",
    "undefined",
}


class URLCreate(BaseModel):
    target_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None
    password: Optional[str] = None

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("target_url must be an absolute HTTP(S) URL")
        return value

    @field_validator("custom_alias")
    @classmethod
    def validate_custom_alias(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if not ALIAS_REGEX.match(trimmed):
            raise ValueError(
                "custom_alias must be 3-50 characters long and contain only letters, numbers, underscores, or hyphens."
            )
        if trimmed.lower() in RESERVED_ALIASES:
            raise ValueError(
                f"'{trimmed}' is a reserved route name and cannot be used as a custom alias."
            )
        return trimmed

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        # Normalize to UTC
        if value.tzinfo is None:
            utc_val = value.replace(tzinfo=timezone.utc)
        else:
            utc_val = value.astimezone(timezone.utc)

        if utc_val <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future.")
        return utc_val


class UserRegister(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Authentication routes
class TokenRefreshRequest(BaseModel):
    refresh_token: str


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(item: UserRegister, request: Request, db: Session = Depends(get_db)):
    if not ENABLE_LEGACY_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy password authentication is disabled. Please use Google authentication.",
        )
    check_rate_limit(f"rate_limit:auth:{get_client_ip(request)}", limit=10, window=60)
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
def login_user(item: UserLogin, request: Request, db: Session = Depends(get_db)):
    if not ENABLE_LEGACY_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy password authentication is disabled. Please use Google authentication.",
        )
    check_rate_limit(f"rate_limit:auth:{get_client_ip(request)}", limit=10, window=60)
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
def refresh_token(
    item: TokenRefreshRequest, request: Request, db: Session = Depends(get_db)
):
    if not ENABLE_LEGACY_AUTH:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy password authentication is disabled. Please use Google authentication.",
        )
    check_rate_limit(f"rate_limit:auth:{get_client_ip(request)}", limit=10, window=60)
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
    limit: int = 50,
    offset: int = 0,
):
    urls = (
        db.query(models.URL)
        .filter(models.URL.user_id == current_user_id)
        .order_by(models.URL.created_at.desc(), models.URL.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": url.id,
            "short_id": url.short_id,
            "target_url": url.target_url,
            "clicks_count": url.clicks_count,
            "created_at": url.created_at,
            "expires_at": url.expires_at,
            "short_url": f"{PUBLIC_BASE_URL}/{url.short_id}",
        }
        for url in urls
    ]


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
        redis_cache.delete(f"url:{short_id}")
    except Exception as e:
        logger.warning(f"Could not clear cache for deleted url {short_id}: {e}")

    return {"detail": "Short URL deleted successfully"}


# URL Shortening endpoint
@app.post("/api/shorten", dependencies=[Depends(rate_limit)])
def create_short_url(
    item: URLCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(security.require_current_user_id),
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
        while (
            short_id in RESERVED_ALIASES
            or db.query(models.URL).filter(models.URL.short_id == short_id).first()
        ):
            short_id = generate_short_id()

    # Secure password with bcrypt if provided
    hashed_pwd = security.hash_link_password(item.password) if item.password else None

    try:
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
    except IntegrityError as exc:
        db.rollback()
        logger.warning(f"Conflict on short link creation: {exc}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alias already in use. Please select another alias.",
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Database error on short link creation: {exc}")
        raise
    logger.info(
        f"Short link created: {short_id} -> {target_url_str} (User: {current_user_id})"
    )

    ttl_seconds = 86400  # Default 24 hours
    if item.expires_at:
        seconds_left = int(
            (item.expires_at - datetime.now(timezone.utc)).total_seconds()
        )
        if 0 < seconds_left < ttl_seconds:
            ttl_seconds = seconds_left

    cache_data = {
        "target_url": target_url_str,
        "password": bool(hashed_pwd),
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
    }
    try:
        redis_cache.set(f"url:{short_id}", json.dumps(cache_data), ex=ttl_seconds)
    except Exception as e:
        logger.warning(f"Could not write cache entry for {short_id}: {e}")

    return {
        "short_id": short_id,
        "target_url": target_url_str,
        "short_url": f"{PUBLIC_BASE_URL}/{short_id}",
    }


def get_html_template(title: str, body_content: str) -> str:
    escaped_title = html.escape(title)
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{escaped_title}</title>
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
</html>"""


# Redirection endpoints
@app.api_route("/{short_id}", methods=["GET", "HEAD"])
def redirect_url(
    short_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if short_id in RESERVED_ALIASES:
        raise HTTPException(status_code=404, detail="Not Found")

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

        # Write to Cache with appropriate TTL
        ttl_seconds = 86400
        if expires_at:
            exp_utc = (
                expires_at
                if expires_at.tzinfo
                else expires_at.replace(tzinfo=timezone.utc)
            )
            seconds_left = int((exp_utc - datetime.now(timezone.utc)).total_seconds())
            if 0 < seconds_left < ttl_seconds:
                ttl_seconds = seconds_left

        cache_data = {
            "target_url": target_url,
            "password": password,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        try:
            redis_cache.set(f"url:{short_id}", json.dumps(cache_data), ex=ttl_seconds)
        except Exception as e:
            logger.warning(f"Could not update cache: {e}")

    # Expiry verification
    if expires_at:
        exp_utc = (
            expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        )
        if datetime.now(timezone.utc) > exp_utc:
            logger.info(f"Access attempt to expired link: {short_id}")
            if request.method == "HEAD":
                return Response(status_code=200)
            return HTMLResponse(
                get_html_template(
                    "Link Expired",
                    "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                )
            )

    # HEAD request handling: return redirect headers without click tracking or body
    if request.method == "HEAD":
        if password:
            return Response(
                status_code=200,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        return Response(status_code=307, headers={"Location": target_url})

    # Render unlock page if password is set
    if password:
        escaped_short_id = html.escape(short_id)
        form = f"""
            <h2>Unlock Link</h2>
            <p style="color: #94a3b8; font-size: 0.9em; margin-bottom: 1.5rem;">This link is password protected.</p>
            <form method="post" action="/{escaped_short_id}">
                <input type="password" name="password" placeholder="Enter password" required />
                <button type="submit">Unlock</button>
            </form>
        """
        return HTMLResponse(get_html_template("Password Required", form))

    user_agent = request.headers.get("user-agent", "Unknown")
    ip = get_client_ip(request)
    background_tasks.add_task(track_click, short_id, user_agent, ip)

    return RedirectResponse(url=target_url)


@app.post("/{short_id}")
def verify_password_and_redirect(
    short_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    password: str = Form(...),
):
    ip = get_client_ip(request)
    # Rate limit password unlock attempts: 5 attempts per min per IP + short_id
    check_rate_limit(f"rate_limit:unlock:{ip}:{short_id}", limit=5, window=60)

    url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    # Expiry verification
    if url.expires_at:
        exp_utc = (
            url.expires_at
            if url.expires_at.tzinfo
            else url.expires_at.replace(tzinfo=timezone.utc)
        )
        if datetime.now(timezone.utc) > exp_utc:
            return HTMLResponse(
                get_html_template(
                    "Link Expired",
                    "<h2>Link Expired</h2><p>This short URL is no longer active.</p>",
                )
            )

    # Password check
    if url.password:
        if not security.verify_link_password(password, url.password):
            escaped_short_id = html.escape(short_id)
            form = f"""
                <h2>Unlock Link</h2>
                <p style="color: #94a3b8; font-size: 0.9em; margin-bottom: 1.5rem;">This link is password protected.</p>
                <form method="post" action="/{escaped_short_id}">
                    <input type="password" name="password" placeholder="Enter password" required />
                    <button type="submit">Unlock</button>
                    <div class="error">Incorrect password. Please try again.</div>
                </form>
            """
            return HTMLResponse(get_html_template("Password Required", form))

        # Seamless re-hash: migrate legacy SHA-256 to bcrypt upon successful unlock
        if security.link_password_needs_rehash(url.password):
            url.password = security.hash_link_password(password)
            try:
                db.commit()
                db.refresh(url)
                logger.info(
                    f"Migrated legacy link password to bcrypt for short_id: {short_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Could not re-hash legacy link password for {short_id}: {e}"
                )
                db.rollback()

    user_agent = request.headers.get("user-agent", "Unknown")
    background_tasks.add_task(track_click, short_id, user_agent, ip)

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


def _verify_ws_token_and_get_stats(token: str, short_id: str):
    """Synchronous helper run off the event loop for WebSocket auth and DB lookup."""
    with SessionLocal() as db:
        user = security.get_current_user_from_token(token, db)
        if not user:
            return None, "Authentication required"
        url = db.query(models.URL).filter(models.URL.short_id == short_id).first()
        if not url or url.user_id != user.id:
            return None, "Link not found or unauthorized"
        return compile_stats(url, db), None


# Live WebSockets endpoint stats
@app.websocket("/api/ws/stats/{short_id}")
async def websocket_stats(websocket: WebSocket, short_id: str):
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not token:
        try:
            # Wait for first auth JSON frame: {"type": "auth", "token": "..."}
            auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
            if isinstance(auth_msg, dict) and auth_msg.get("type") == "auth":
                token = auth_msg.get("token")
        except Exception:
            await websocket.close(
                code=1008, reason="Authentication timeout or invalid handshake"
            )
            return

    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return

    # Run DB resolution off the event loop so async loop is not blocked
    initial_stats, error_reason = await run_in_threadpool(
        _verify_ws_token_and_get_stats, token, short_id
    )
    if error_reason:
        await websocket.close(code=1008, reason=error_reason)
        return

    await manager.connect(short_id, websocket)
    try:
        await websocket.send_json({"type": "initial_stats", "data": initial_stats})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(short_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error on {short_id}: {e}")
        manager.disconnect(short_id, websocket)
