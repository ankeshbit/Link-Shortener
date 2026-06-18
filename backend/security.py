import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

load_dotenv()

# JWT configuration

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if "pytest" in sys.modules or os.getenv("TESTING") == "true":
        SECRET_KEY = "test-secret-key-for-pytest-runs"
    else:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. Please configure it in your environment."
        )

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


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
    """Creates a JWT access token containing payload data, type and expiration date."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Creates a JWT refresh token containing payload data, type and expiration date."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default to 7 days
        expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decodes a JWT access token, verifying its validity, type, and expiration."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict | None:
    """Decodes a JWT refresh token, verifying its validity, type, and expiration."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


# OAuth2 scheme configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int | None:
    """Extracts and verifies the user ID from the JWT authorization token in the request header."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    try:
        return int(user_id)
    except ValueError:
        return None
