import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure backend path is configured
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Base, engine
from main import app
from redis_client import redis_cache

client = TestClient(app)


# Helper to check if database is connected/alive
def database_alive():
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def register_token(prefix="testuser"):
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"{prefix}_{os.urandom(4).hex()}@bytelink.co",
            "password": "SuperSecurePassword123!",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


# Safely skip drop_all to preserve database records and URL ownership
@pytest.fixture(autouse=True)
def clean_db():
    # Production/Neon protection: Do not drop tables
    yield


def test_health_check():
    """Asserts healthcheck endpoint returns status information."""
    response = client.get("/health")
    # Health check could be 200 or 503 depending on database availability
    assert response.status_code in [200, 503]
    if response.status_code == 200:
        assert response.json()["status"] == "healthy"


def test_root_endpoint():
    """Asserts that root landing endpoint returns status 200 and success details."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "ByteLink API is running successfully"
    assert data["status"] == "healthy"
    assert data["docs"] == "/docs"
    assert data["redoc"] == "/redoc"
    assert data["health"] == "/health"
    assert data["version"] == "1.0.0"


def test_invalid_short_url_404():
    """Asserts that non-existent short URL returns 404 error."""
    response = client.get("/nonexistent-short-id-12345")
    assert response.status_code == 404


def test_account_features_require_authentication():
    """Account-owned link operations must reject unauthenticated requests."""
    assert client.post(
        "/api/shorten", json={"target_url": "https://example.com"}
    ).status_code == 401
    assert client.get("/api/user/links").status_code == 401
    assert client.get("/api/stats/not-a-link").status_code == 401


def test_favicon_404():
    """Asserts favicon query returns 404 without redirect processing."""
    response = client.get("/favicon.ico")
    assert response.status_code == 404


def test_api_docs_reachable():
    """Asserts OpenAPI documentation interface loads correctly."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_user_registration_invalid_email():
    """Asserts that registering with an invalid email format raises a validation error (422)."""
    response = client.post(
        "/api/auth/register",
        json={"email": "invalid-email-format", "password": "securepassword123"},
    )
    assert response.status_code == 422


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_auth_registration_and_login():
    """Tests full register, login, refresh, and get_me auth flow."""
    email = f"testuser_{os.urandom(4).hex()}@bytelink.co"
    password = "SuperSecurePassword123!"

    # 1. Register
    reg_resp = client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert "refresh_token" in reg_data

    # 2. Login
    log_resp = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert log_resp.status_code == 200
    log_data = log_resp.json()
    assert "access_token" in log_data
    access_token = log_data["access_token"]
    refresh_token = log_data["refresh_token"]
    assert access_token is not None

    # 3. Refresh Token
    ref_resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_resp.status_code == 200
    ref_data = ref_resp.json()
    assert "access_token" in ref_data
    new_access_token = ref_data["access_token"]

    # 4. Get Current User Me (success)
    me_resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_short_link_flow():
    """Tests authenticated creation while keeping redirect resolution public."""
    headers = {"Authorization": f"Bearer {register_token('shortener')}"}
    alias = f"alias_{os.urandom(4).hex()}"
    target = "https://google.com"

    # Anonymous creation is no longer an account-free operation.
    assert client.post("/api/shorten", json={"target_url": target}).status_code == 401

    # Authenticated users can create short URLs.
    create_resp = client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias},
        headers=headers,
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["short_id"] == alias
    assert (
        create_data["target_url"] == target + "/" or create_data["target_url"] == target
    )

    # 2. Re-create same alias, expect conflict 409
    conflict_resp = client.post(
        "/api/shorten",
        json={"target_url": "https://yahoo.com", "custom_alias": alias},
        headers=headers,
    )
    assert conflict_resp.status_code == 409

    # 3. Try to access redirect URL, expect 307/303 redirect
    redirect_resp = client.get(f"/{alias}", follow_redirects=False)
    assert redirect_resp.status_code in [302, 303, 307]
    assert (
        redirect_resp.headers["location"] == target + "/"
        or redirect_resp.headers["location"] == target
    )


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_password_protected_short_link():
    """Asserts that password protected link requires credential matching to redirect."""
    alias = f"pwd_link_{os.urandom(4).hex()}"
    target = "https://wikipedia.org"
    password = "mysecretpassword"

    # 1. Create password link
    create_resp = client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias, "password": password},
        headers={"Authorization": f"Bearer {register_token('password')}"},
    )
    assert create_resp.status_code == 200

    # 2. Attempt redirect without password, should return unlock prompt HTML
    redirect_resp = client.get(f"/{alias}")
    assert redirect_resp.status_code == 200
    assert "Password Required" in redirect_resp.text

    # 3. Attempt unlock with incorrect password
    unlock_fail_resp = client.post(f"/{alias}", data={"password": "wrongpassword"})
    assert unlock_fail_resp.status_code == 200
    assert "Incorrect password" in unlock_fail_resp.text

    # 4. Attempt unlock with correct password, should redirect
    unlock_success_resp = client.post(
        f"/{alias}", data={"password": password}, follow_redirects=False
    )
    assert unlock_success_resp.status_code in [302, 303, 307]
    assert (
        unlock_success_resp.headers["location"] == target + "/"
        or unlock_success_resp.headers["location"] == target
    )


def test_cache_unavailable_does_not_fabricate_data():
    """Redis absence must not create an in-memory application-data source."""
    if redis_cache.client is None:
        assert redis_cache.get("missing-test-key") is None
        assert redis_cache.incr("missing-test-counter") is None
        return

    redis_cache.set("test_key", "test_value", ex=5)
    assert redis_cache.get("test_key") == "test_value"
    assert redis_cache.incr("test_counter") >= 1


from unittest.mock import patch


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_firebase_token_authentication_and_user_creation():
    """Tests that a verified Firebase ID token authenticates the user, creates a Neon record, and provides access."""
    mock_uid = f"firebase_uid_{os.urandom(4).hex()}"
    mock_email = f"user_{mock_uid}@example.com"

    mock_claims = {
        "uid": mock_uid,
        "email": mock_email,
        "name": "Firebase User",
        "email_verified": True,
    }

    with patch("firebase_config.auth.verify_id_token", return_value=mock_claims):
        token = "mock-firebase-id-token"
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Sync / Me endpoint
        me_resp = client.get("/api/auth/me", headers=headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["firebase_uid"] == mock_uid
        assert me_data["email"] == mock_email
        user_id = me_data["id"]

        # 2. Subsequent call reuses the same user_id
        me_resp2 = client.post("/api/auth/sync", headers=headers)
        assert me_resp2.status_code == 200
        assert me_resp2.json()["id"] == user_id

        # 3. Create short link
        alias = f"fb_{os.urandom(4).hex()}"
        short_resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.org", "custom_alias": alias},
            headers=headers,
        )
        assert short_resp.status_code == 200

        # 4. User links contains the link
        links_resp = client.get("/api/user/links", headers=headers)
        assert links_resp.status_code == 200
        user_short_ids = [l["short_id"] for l in links_resp.json()]
        assert alias in user_short_ids

        # 5. Delete link
        del_resp = client.delete(f"/api/user/links/{alias}", headers=headers)
        assert del_resp.status_code == 200


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_firebase_user_isolation():
    """Tests that User B cannot access or delete User A's links."""
    uid_a = f"fb_user_a_{os.urandom(4).hex()}"
    uid_b = f"fb_user_b_{os.urandom(4).hex()}"

    alias = f"link_a_{os.urandom(4).hex()}"

    with patch("firebase_config.auth.verify_id_token", return_value={"uid": uid_a, "email": f"{uid_a}@test.co"}):
        create_resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com/a", "custom_alias": alias},
            headers={"Authorization": "Bearer token-a"},
        )
        assert create_resp.status_code == 200

    # User B attempts to access User A's stats and delete User A's link
    with patch("firebase_config.auth.verify_id_token", return_value={"uid": uid_b, "email": f"{uid_b}@test.co"}):
        stats_resp = client.get(f"/api/stats/{alias}", headers={"Authorization": "Bearer token-b"})
        assert stats_resp.status_code == 404

        del_resp = client.delete(f"/api/user/links/{alias}", headers={"Authorization": "Bearer token-b"})
        assert del_resp.status_code == 404

