import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from database import get_db
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from firebase_config import verify_firebase_id_token
from jose import JWTError, jwt
from loguru import logger
import models
from sqlalchemy.orm import Session

load_dotenv()

# Legacy JWT configuration (optional during migration / fallback)
JWT_SECRET = os.getenv("JWT_SECRET", "bytelink-legacy-secret-key-fallback")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_link_password(password: str) -> str:
    """Hashes a short-link password using SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_link_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain short-link password against its SHA-256 hash."""
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == hashed_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against its bcrypt hashed value."""
    if not hashed_password or not plain_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generates a secure bcrypt hash of a plain text password."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Legacy helper: Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Legacy helper: Creates a JWT refresh token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decodes a legacy JWT access token if applicable."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict | None:
    """Decodes a legacy JWT refresh token if applicable."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


# OAuth2 scheme configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def get_or_create_user_from_firebase(db: Session, firebase_info: dict) -> models.User:
    """
    Finds or creates a Neon application user using verified Firebase claims.
    - If user exists by firebase_uid -> returns user.
    - If user exists by verified email without firebase_uid -> links firebase_uid and returns user.
    - Otherwise -> creates a new user record in Neon and returns it.
    """
    uid = firebase_info.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token missing UID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = firebase_info.get("email")

    # 1. Lookup by firebase_uid
    user = db.query(models.User).filter(models.User.firebase_uid == uid).first()
    if user:
        if email and user.email != email:
            try:
                user.email = email
                db.commit()
                db.refresh(user)
            except Exception:
                db.rollback()
        return user

    # 2. Match existing account by verified email to preserve URLs and ownership
    if email:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user:
            logger.info(
                f"Linking existing user account ID {user.id} ({email}) with firebase_uid: {uid}"
            )
            user.firebase_uid = uid
            db.commit()
            db.refresh(user)
            return user

    # 3. Create new user in Neon
    logger.info(f"Creating new Neon user for firebase_uid: {uid} ({email})")
    user = models.User(
        email=email or f"{uid}@firebase.user",
        firebase_uid=uid,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """
    Dependency that extracts and verifies the identity from the Authorization Bearer token.
    Verifies Firebase ID token, resolves the user in Neon DB, and returns the User model instance.
    """
    if not token:
        return None

    firebase_info = verify_firebase_id_token(token)
    if firebase_info:
        return get_or_create_user_from_firebase(db, firebase_info)

    # Legacy token fallback (e.g. for existing automated test suite compatibility)
    payload = decode_access_token(token)
    if payload and payload.get("sub"):
        try:
            user_id = int(payload["sub"])
            return db.query(models.User).filter(models.User.id == user_id).first()
        except (ValueError, TypeError):
            pass

    return None


def get_current_user_id(
    user: Optional[models.User] = Depends(get_current_user),
) -> Optional[int]:
    """Extracts the integer user ID from the resolved authenticated user."""
    return user.id if user else None


def require_current_user(
    user: Optional[models.User] = Depends(get_current_user),
) -> models.User:
    """Requires an authenticated user or raises HTTP 401."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_current_user_id(
    user: models.User = Depends(require_current_user),
) -> int:
    """Requires a valid authenticated user and returns their Neon user.id."""
    return user.id


def get_current_user_from_token(
    token: Optional[str], db: Session
) -> Optional[models.User]:
    """Validates an authentication token supplied outside FastAPI dependency injection."""
    if not token:
        return None

    firebase_info = verify_firebase_id_token(token)
    if firebase_info:
        return get_or_create_user_from_firebase(db, firebase_info)

    # Legacy token fallback
    payload = decode_access_token(token)
    if payload and payload.get("sub"):
        try:
            user_id = int(payload["sub"])
            return db.query(models.User).filter(models.User.id == user_id).first()
        except (ValueError, TypeError):
            pass

    return None


def get_current_user_id_from_token(
    token: Optional[str], db: Optional[Session] = None
) -> Optional[int]:
    """Validates token and returns integer user ID, opening a DB session if needed."""
    if not token:
        return None

    if db is not None:
        user = get_current_user_from_token(token, db)
        return user.id if user else None

    from database import SessionLocal

    with SessionLocal() as session:
        user = get_current_user_from_token(token, session)
        return user.id if user else None
