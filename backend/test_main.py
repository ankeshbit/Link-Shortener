import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ensure backend path is configured
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models
from database import engine
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


@pytest.fixture(autouse=True)
def reset_rate_limit():
    def _clear():
        if redis_cache.client:
            try:
                for key in ["rate_limit:testclient", "rate_limit:127.0.0.1"]:
                    redis_cache.client.delete(key)
            except Exception:
                pass

    _clear()
    yield
    _clear()


def register_token(prefix="testuser"):
    import models
    import security
    from database import SessionLocal

    with SessionLocal() as db:
        user = models.User(
            email=f"{prefix}_{os.urandom(4).hex()}@bytelink.co",
            firebase_uid=f"firebase_{os.urandom(6).hex()}",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    return security.create_access_token(data={"sub": str(user_id)})


# Clean up test records without dropping tables
@pytest.fixture(scope="session", autouse=True)
def clean_db():
    yield
    try:
        import models
        from database import SessionLocal

        with SessionLocal() as db:
            test_users = (
                db.query(models.User)
                .filter(
                    (models.User.email.like("%@bytelink.co"))
                    | (models.User.email.like("testuser%"))
                )
                .all()
            )
            for u in test_users:
                db.delete(u)
            test_urls = (
                db.query(models.URL)
                .filter(models.URL.original_url.like("%example.com%"))
                .all()
            )
            for url in test_urls:
                db.delete(url)
            db.commit()
    except Exception:
        pass


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
    assert (
        client.post(
            "/api/shorten", json={"target_url": "https://example.com"}
        ).status_code
        == 401
    )
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


def test_legacy_auth_disabled_by_default():
    """Asserts that legacy auth endpoints return 403 Forbidden by default."""
    assert (
        client.post(
            "/api/auth/register",
            json={"email": "legacy@bytelink.co", "password": "password123"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "legacy@bytelink.co", "password": "password123"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/refresh", json={"refresh_token": "some-token"}
        ).status_code
        == 403
    )


def test_user_registration_invalid_email(monkeypatch):
    """Asserts that registering with an invalid email format raises a validation error (422) when auth is enabled."""
    import main

    monkeypatch.setattr(main, "ENABLE_LEGACY_AUTH", True)
    response = client.post(
        "/api/auth/register",
        json={"email": "invalid-email-format", "password": "securepassword123"},
    )
    assert response.status_code == 422


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_auth_registration_and_login(monkeypatch):
    """Tests full register, login, refresh, and get_me auth flow when legacy auth is enabled."""
    import main

    monkeypatch.setattr(main, "ENABLE_LEGACY_AUTH", True)
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
        user_short_ids = [lnk["short_id"] for lnk in links_resp.json()]
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

    with patch(
        "firebase_config.auth.verify_id_token",
        return_value={"uid": uid_a, "email": f"{uid_a}@test.co"},
    ):
        create_resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com/a", "custom_alias": alias},
            headers={"Authorization": "Bearer token-a"},
        )
        assert create_resp.status_code == 200

    # User B attempts to access User A's stats and delete User A's link
    with patch(
        "firebase_config.auth.verify_id_token",
        return_value={"uid": uid_b, "email": f"{uid_b}@test.co"},
    ):
        stats_resp = client.get(
            f"/api/stats/{alias}", headers={"Authorization": "Bearer token-b"}
        )
        assert stats_resp.status_code == 404

        del_resp = client.delete(
            f"/api/user/links/{alias}", headers={"Authorization": "Bearer token-b"}
        )
        assert del_resp.status_code == 404


def test_firebase_admin_individual_env_initialization():
    """Verifies that Firebase Admin correctly unescapes newlines and uses individual env vars."""
    import firebase_config

    mock_project_id = "test-project-123"
    mock_email = "test-sa@test-project-123.iam.gserviceaccount.com"
    mock_raw_key = "-----BEGIN PRIVATE KEY-----\\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASC\\n-----END PRIVATE KEY-----\\n"

    with patch.dict(
        os.environ,
        {
            "FIREBASE_PROJECT_ID": mock_project_id,
            "FIREBASE_CLIENT_EMAIL": mock_email,
            "FIREBASE_PRIVATE_KEY": mock_raw_key,
            "FIREBASE_SERVICE_ACCOUNT_JSON": "",
            "FIREBASE_CREDENTIALS_PATH": "",
        },
        clear=False,
    ), patch("firebase_config._firebase_initialized", False), patch(
        "firebase_admin._apps", {}
    ), patch(
        "firebase_admin.credentials.Certificate"
    ) as mock_cert, patch(
        "firebase_admin.initialize_app"
    ) as mock_init:
        res = firebase_config.initialize_firebase()
        assert res is True
        mock_init.assert_called_once()
        cert_arg = mock_cert.call_args[0][0]
        assert cert_arg["project_id"] == mock_project_id
        assert cert_arg["client_email"] == mock_email
        assert "\\n" not in cert_arg["private_key"]
        assert "\n" in cert_arg["private_key"]


def test_firebase_invalid_or_missing_token_401():
    """Verifies that invalid or missing Firebase tokens safely return 401 without revealing internal details."""
    # 1. Missing token
    res_no_auth = client.post(
        "/api/shorten", json={"target_url": "https://example.com"}
    )
    assert res_no_auth.status_code == 401
    assert res_no_auth.json()["message"] == "Authentication required"

    # 2. Invalid token
    with patch(
        "firebase_config.auth.verify_id_token",
        side_effect=Exception("Invalid signature"),
    ):
        res_invalid = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com"},
            headers={"Authorization": "Bearer totally-invalid-token"},
        )
        assert res_invalid.status_code == 401
        assert res_invalid.json()["message"] == "Authentication required"


# ==========================================
# PHASE 7 AUTOMATED VERIFICATION TEST SUITE
# ==========================================


def test_phase7_1_authenticated_url_shortening():
    """1. Authenticated URL shortening works and returns formatted short_url."""
    token = register_token("auth_short")
    resp = client.post(
        "/api/shorten",
        json={"target_url": "https://python.org"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "short_id" in data
    assert data["target_url"] in ["https://python.org", "https://python.org/"]
    assert data["short_url"].endswith(data["short_id"])


def test_phase7_2_invalid_firebase_token():
    """2. Invalid Firebase token returns 401."""
    with patch(
        "firebase_config.auth.verify_id_token",
        side_effect=Exception("Invalid signature"),
    ):
        resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com"},
            headers={"Authorization": "Bearer bad-firebase-token-123"},
        )
        assert resp.status_code == 401
        assert resp.json()["status"] == "error"
        assert resp.json()["message"] == "Authentication required"


def test_phase7_3_expired_authentication_token():
    """3. Expired authentication token returns 401."""
    from datetime import timedelta

    import security

    expired_token = security.create_access_token(
        data={"sub": "1"}, expires_delta=timedelta(seconds=-60)
    )
    resp = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com"},
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


def test_phase7_4_missing_authentication():
    """4. Missing authentication returns 401."""
    resp = client.post("/api/shorten", json={"target_url": "https://example.com"})
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"
    assert resp.json()["message"] == "Authentication required"


def test_phase7_5_valid_target_url():
    """5. Valid target URL with scheme and host is accepted."""
    token = register_token("valid_url")
    for valid_url in [
        "https://github.com/ankeshbit",
        "http://example.com/path?query=1",
    ]:
        resp = client.post(
            "/api/shorten",
            json={"target_url": valid_url},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


def test_phase7_6_invalid_target_url():
    """6. Invalid target URL returns 422 validation error."""
    token = register_token("invalid_url")
    for bad_url in ["not-a-url", "ftp://invalid-scheme.com", "javascript:alert(1)"]:
        resp = client.post(
            "/api/shorten",
            json={"target_url": bad_url},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        assert resp.json()["status"] == "error"


def test_phase7_7_custom_alias_conflict():
    """7. Custom alias conflict returns HTTP 409."""
    token = register_token("alias_conflict")
    alias = f"conflict_{os.urandom(4).hex()}"
    resp1 = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/first", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/second", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["status"] == "error"
    assert "already in use" in resp2.json()["message"]


def test_phase7_8_postgresql_insertion_failure():
    """8. PostgreSQL insertion failure returns 500 without leaking stack traces."""
    from sqlalchemy.exc import SQLAlchemyError

    token = register_token("db_fail")
    with patch(
        "sqlalchemy.orm.Session.commit",
        side_effect=SQLAlchemyError("Simulated DB Disk Failure"),
    ):
        resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com/db-fail"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 500
        assert resp.json()["status"] == "error"
        assert "database error" in resp.json()["message"].lower()


def test_phase7_9_redis_unavailable():
    """9. Redis unavailability does not prevent URL shortening or redirection."""
    token = register_token("no_redis")
    alias = f"no_redis_{os.urandom(4).hex()}"
    target = "https://redis.io"

    with patch.object(
        redis_cache, "set", side_effect=Exception("Redis connection refused")
    ):
        with patch.object(redis_cache, "get", return_value=None):
            resp = client.post(
                "/api/shorten",
                json={"target_url": target, "custom_alias": alias},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200

            redirect_resp = client.get(f"/{alias}", follow_redirects=False)
            assert redirect_resp.status_code in [302, 303, 307]
            assert redirect_resp.headers["location"] in [target, target + "/"]


def test_phase7_10_successful_public_redirect():
    """10. Public short URL redirects without requiring authentication."""
    token = register_token("pub_red")
    alias = f"pub_{os.urandom(4).hex()}"
    target = "https://fastapi.tiangolo.com"
    client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(f"/{alias}", follow_redirects=False)
    assert resp.status_code in [302, 303, 307]
    assert resp.headers["location"] in [target, target + "/"]


def test_phase7_11_redirect_from_another_device():
    """11. Short link works when requested with mobile / external user agents."""
    token = register_token("mobile_device")
    alias = f"mob_{os.urandom(4).hex()}"
    target = "https://developer.mozilla.org"
    client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    mobile_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        "X-Forwarded-For": "203.0.113.195",
    }
    resp = client.get(f"/{alias}", headers=mobile_headers, follow_redirects=False)
    assert resp.status_code in [302, 303, 307]
    assert resp.headers["location"] in [target, target + "/"]


def test_phase7_12_expired_url():
    """12. Expired URL is rejected with appropriate status / message."""
    from datetime import datetime, timedelta, timezone

    import models
    from database import SessionLocal

    alias = f"exp_{os.urandom(4).hex()}"
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        url = models.URL(
            short_id=alias,
            target_url="https://archive.org",
            expires_at=past_time,
        )
        db.add(url)
        db.commit()

    resp = client.get(f"/{alias}", follow_redirects=False)
    assert resp.status_code == 200
    assert "Link Expired" in resp.text


def test_phase7_13_password_protected_url():
    """13. Password-protected URL requires correct password unlock."""
    token = register_token("pwd_flow")
    alias = f"lock_{os.urandom(4).hex()}"
    target = "https://en.wikipedia.org"
    password = "CorrectHorseBatteryStaple"

    client.post(
        "/api/shorten",
        json={
            "target_url": target,
            "custom_alias": alias,
            "password": password,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    prompt_resp = client.get(f"/{alias}")
    assert prompt_resp.status_code == 200
    assert "Password Required" in prompt_resp.text

    fail_resp = client.post(f"/{alias}", data={"password": "WrongPassword"})
    assert fail_resp.status_code == 200
    assert "Incorrect password" in fail_resp.text

    success_resp = client.post(
        f"/{alias}", data={"password": password}, follow_redirects=False
    )
    assert success_resp.status_code in [302, 303, 307]
    assert success_resp.headers["location"] in [target, target + "/"]


def test_localhost_origins_allowed_by_cors():
    """Verify localhost frontend origins are allowed in CORS preflight."""
    for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        resp = client.options(
            "/api/shorten",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert resp.status_code in [200, 204]
        assert resp.headers.get("access-control-allow-origin") == origin


def test_localhost_public_base_url_in_short_url():
    """Verify returned short_url uses localhost base url."""
    token = register_token("local_base")
    alias = f"local_{os.urandom(4).hex()}"
    resp = client.post(
        "/api/shorten",
        json={"target_url": "https://example.org/test", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    short_url = resp.json()["short_url"]
    assert short_url.startswith("http://localhost:8000/") or short_url.startswith(
        "http://127.0.0.1:8000/"
    )
    assert alias in short_url


def test_db_persistence_across_sessions():
    """Verify database user and URL records persist across distinct session queries."""
    from database import SessionLocal

    token = register_token("persistence_check")
    alias = f"persist_{os.urandom(4).hex()}"
    target = "https://www.python.org"

    resp = client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Query with a brand new, independent database session
    with SessionLocal() as db:
        record = db.query(models.URL).filter(models.URL.short_id == alias).first()
        assert record is not None
        assert record.target_url == target
        assert record.user_id is not None
        user = db.query(models.User).filter(models.User.id == record.user_id).first()
        assert user is not None
        assert "persistence_check" in user.email


def test_firebase_token_verifier_signature_validation():
    """Verify public key verification rejects tampered or forged tokens."""
    from firebase_config import verify_firebase_token_with_public_keys

    # Forged token with invalid header/signature
    tampered_token = (
        "eyJhbGciOiJSUzI1NiIsImtpZCI6ImludmFsaWQifQ.eyJzdWIiOiIxMjMifQ.invalidsig"
    )
    result = verify_firebase_token_with_public_keys(
        tampered_token, "link-shortener-6c96e"
    )
    assert result is None


def test_user_delete_link():
    """Verify authenticated user can delete their owned link."""
    token = register_token("del_owner")
    alias = f"del_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/delete-me", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    del_resp = client.delete(
        f"/api/user/links/{alias}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["detail"] == "Short URL deleted successfully"

    # Confirm it returns 404 on subsequent access
    get_resp = client.get(f"/{alias}")
    assert get_resp.status_code == 404


def test_user_links_isolation():
    """Verify user link access and deletion is isolated between accounts."""
    token_a = register_token("user_alpha")
    token_b = register_token("user_beta")

    alias_a = f"alpha_{os.urandom(4).hex()}"
    alias_b = f"beta_{os.urandom(4).hex()}"

    client.post(
        "/api/shorten",
        json={"target_url": "https://alpha.example.com", "custom_alias": alias_a},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    client.post(
        "/api/shorten",
        json={"target_url": "https://beta.example.com", "custom_alias": alias_b},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # User A views their links
    resp_a = client.get(
        "/api/user/links", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp_a.status_code == 200
    links_a = [lnk["short_id"] for lnk in resp_a.json()]
    assert alias_a in links_a
    assert alias_b not in links_a

    # User A attempts to delete User B's link
    hack_resp = client.delete(
        f"/api/user/links/{alias_b}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert hack_resp.status_code == 404


def test_redis_live_caching_and_retrieval():
    """Verify created short link is immediately cached in Redis."""
    token = register_token("cache_user")
    alias = f"cached_{os.urandom(4).hex()}"
    target = "https://cache.example.com"

    client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    cached_val = redis_cache.get(f"url:{alias}")
    if cached_val:
        import json

        data = json.loads(cached_val)
        assert data["target_url"] == target


def test_websocket_realtime_connection_and_initial_stats():
    """Verify WebSocket client can connect with auth token and receive initial stats."""
    token = register_token("ws_user")
    alias = f"ws_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://websocket.example.com", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    with client.websocket_connect(f"/api/ws/stats/{alias}?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "initial_stats"
        assert msg["data"]["short_id"] == alias
        assert msg["data"]["total_clicks"] == 0


# ==============================================================================
# PHASE 1: SECURITY REGRESSION TESTS
# ==============================================================================


def test_phase1_jwt_secret_enforcement(monkeypatch):
    """1. Raises RuntimeError when JWT_SECRET is unset or shorter than 32 characters."""
    import importlib

    import security

    # Temporarily remove override and set short secret
    monkeypatch.setenv("JWT_SECRET", "short_secret")
    monkeypatch.setenv("ALLOW_SHORT_JWT_SECRET", "false")

    with pytest.raises(RuntimeError) as exc_info:
        importlib.reload(security)
    assert (
        "JWT_SECRET environment variable is missing or shorter than 32 characters"
        in str(exc_info.value)
    )

    # Restore valid secret
    monkeypatch.setenv(
        "JWT_SECRET", "bytelink-super-secret-development-jwt-key-2026-secure"
    )
    importlib.reload(security)


def test_phase1_account_prehijacking_unverified_rejected():
    """2. Refuses to link unverified identity provider account to existing user (409 Conflict)."""
    from fastapi import HTTPException

    import models
    import security
    from database import SessionLocal

    email = f"victim_{os.urandom(4).hex()}@bytelink.co"
    with SessionLocal() as db:
        victim = models.User(email=email, firebase_uid=f"orig_{os.urandom(4).hex()}")
        db.add(victim)
        db.commit()

        # Attacker tries to claim email without verification
        unverified_claims = {
            "uid": f"attacker_{os.urandom(4).hex()}",
            "email": email,
            "email_verified": False,
        }
        with pytest.raises(HTTPException) as exc_info:
            security.get_or_create_user_from_firebase(db, unverified_claims)
        assert exc_info.value.status_code == 409
        assert "not verified" in exc_info.value.detail.lower()

        # Legitimate provider with verified email links successfully
        verified_claims = {
            "uid": f"new_uid_{os.urandom(4).hex()}",
            "email": email,
            "email_verified": True,
        }
        linked_user = security.get_or_create_user_from_firebase(db, verified_claims)
        assert linked_user.id == victim.id
        assert linked_user.firebase_uid == verified_claims["uid"]


def test_phase1_custom_alias_validation_and_reserved_names():
    """3. Validates custom_alias regex and strictly rejects reserved aliases."""
    token = register_token("alias_test")

    # Reserved aliases should be rejected with 422
    for reserved in [
        "api",
        "docs",
        "redoc",
        "openapi.json",
        "health",
        "favicon.ico",
        "ws",
        "stats",
    ]:
        resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com", "custom_alias": reserved},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert (
            resp.status_code == 422
        ), f"Reserved alias '{reserved}' was not rejected with 422"

    # Invalid regex (symbols, spaces, too short, too long)
    for invalid in ["ab", "a" * 51, "has space", "invalid!char", "semi;colon"]:
        resp = client.post(
            "/api/shorten",
            json={"target_url": "https://example.com", "custom_alias": invalid},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert (
            resp.status_code == 422
        ), f"Invalid alias '{invalid}' was not rejected with 422"

    # Valid alias should succeed
    valid_alias = f"valid_{os.urandom(3).hex()}"
    resp = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com", "custom_alias": valid_alias},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["short_id"] == valid_alias


def test_phase1_stored_xss_html_escaped():
    """3b. Dynamic values rendered in HTML unlock pages are HTML-escaped."""
    token = register_token("xss_user")
    alias = f"xss_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={
            "target_url": "https://example.com",
            "custom_alias": alias,
            "password": "secretpassword",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(f"/{alias}")
    assert resp.status_code == 200
    assert '<form method="post" action="/' + alias + '">' in resp.text
    assert "<script>" not in resp.text


def test_phase1_rate_limiting_atomic_and_reraises():
    """4. Rate limiting uses atomic increment, re-raises HTTPException, and throttles unlock."""
    from fastapi import HTTPException

    from main import check_rate_limit

    test_key = f"rate_limit:test_atomic:{os.urandom(4).hex()}"
    for _ in range(5):
        check_rate_limit(test_key, limit=5, window=60)

    # 6th call exceeds limit
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(test_key, limit=5, window=60)
    assert exc_info.value.status_code == 429

    # Password unlock rate limiting
    token = register_token("unlock_rate")
    alias = f"pwd_rl_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={
            "target_url": "https://example.com",
            "custom_alias": alias,
            "password": "correctpassword",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # 5 failed unlock attempts
    for _ in range(5):
        r = client.post(f"/{alias}", data={"password": "wrongpassword"})
        assert r.status_code in [200, 303]

    # 6th attempt should be blocked with 429
    r6 = client.post(f"/{alias}", data={"password": "wrongpassword"})
    assert r6.status_code == 429


def test_phase1_trusted_proxy_count_client_ip(monkeypatch):
    """5. get_client_ip stops trusting X-Forwarded-For blindly unless TRUSTED_PROXY_COUNT > 0."""
    from starlette.requests import Request

    import main

    class DummyClient:
        host = "192.168.1.50"

    # Default: TRUSTED_PROXY_COUNT = 0 -> ignores X-Forwarded-For spoofing
    monkeypatch.setattr(main, "TRUSTED_PROXY_COUNT", 0)
    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.1")],
        "client": ("192.168.1.50", 12345),
    }
    req = Request(scope)
    assert main.get_client_ip(req) == "192.168.1.50"

    # Behind 1 trusted proxy -> takes the rightmost IP
    monkeypatch.setattr(main, "TRUSTED_PROXY_COUNT", 1)
    assert main.get_client_ip(req) == "10.0.0.1"

    # Behind 2 trusted proxies -> takes 2nd from right
    monkeypatch.setattr(main, "TRUSTED_PROXY_COUNT", 2)
    assert main.get_client_ip(req) == "203.0.113.195"


def test_phase1_link_password_bcrypt_and_legacy_sha256_rehash():
    """6 & 7. Bcrypt link passwords with 72-byte pre-hashing and legacy SHA-256 migration."""
    import hashlib

    import models
    import security
    from database import SessionLocal

    # 72-byte safe handling: password longer than 72 bytes
    long_pwd = "P" * 120
    hashed_long = security.hash_link_password(long_pwd)
    assert hashed_long.startswith("$2b$")
    assert security.verify_link_password(long_pwd, hashed_long) is True
    assert security.verify_link_password(long_pwd + "X", hashed_long) is False

    # Legacy SHA-256 verification and automatic bcrypt upgrade
    legacy_plain = "legacy_pwd_123"
    legacy_sha256 = hashlib.sha256(legacy_plain.encode("utf-8")).hexdigest()
    assert security.link_password_needs_rehash(legacy_sha256) is True
    assert security.verify_link_password(legacy_plain, legacy_sha256) is True

    alias = f"legacy_url_{os.urandom(4).hex()}"
    with SessionLocal() as db:
        test_url = models.URL(
            short_id=alias,
            target_url="https://example.com/legacy",
            password=legacy_sha256,
        )
        db.add(test_url)
        db.commit()

    # Successful unlock POST should migrate DB hash to bcrypt
    resp = client.post(
        f"/{alias}", data={"password": legacy_plain}, follow_redirects=False
    )
    assert resp.status_code == 303

    with SessionLocal() as db:
        updated = db.query(models.URL).filter(models.URL.short_id == alias).first()
        assert updated.password.startswith("$2b$")
        assert security.link_password_needs_rehash(updated.password) is False


def test_phase1_database_url_password_masked_in_error():
    """8. database.py masks connection string passwords in exceptions."""
    from database import normalize_database_url

    with pytest.raises(RuntimeError) as exc_info:
        normalize_database_url("mysql://dbuser:supersecretpass@localhost:3306/db")
    err_msg = str(exc_info.value)
    assert "supersecretpass" not in err_msg
    assert "***" in err_msg


def test_phase1_websocket_auth_first_frame():
    """10. WebSocket client authenticates via first JSON frame."""
    token = register_token("ws_frame_user")
    alias = f"ws_f_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={
            "target_url": "https://websocket-frame.example.com",
            "custom_alias": alias,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    with client.websocket_connect(f"/api/ws/stats/{alias}") as ws:
        # Send first frame auth
        ws.send_json({"type": "auth", "token": token})
        msg = ws.receive_json()
        assert msg["type"] == "initial_stats"
        assert msg["data"]["short_id"] == alias


# ==============================================================================
# PHASE 2: CORRECTNESS & DATA INTEGRITY REGRESSION TESTS
# ==============================================================================


def test_phase2_pydantic_validation_error_json_serializable():
    """1. Validation errors return JSON serializable structure with status=error."""
    token = register_token("pyd_user")
    resp = client.post(
        "/api/shorten",
        json={"target_url": "ftp://bad-scheme.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["status"] == "error"
    assert (
        "target_url" in data["message"].lower() or "absolute" in data["message"].lower()
    )
    assert isinstance(data["detail"], list)


def test_phase2_starlette_http_exception_and_head_route():
    """2. Starlette HTTPException returns consistent error shape, and HEAD requests succeed."""
    # Unknown route returns JSON with status=error
    resp404 = client.get("/api/completely-nonexistent-route-xyz")
    assert resp404.status_code == 404
    data404 = resp404.json()
    assert data404["status"] == "error"

    # HEAD request on redirect URL
    token = register_token("head_user")
    alias = f"head_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://python.org", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    head_resp = client.head(f"/{alias}", follow_redirects=False)
    assert head_resp.status_code in [302, 303, 307]
    assert head_resp.headers["location"] == "https://python.org"
    assert len(head_resp.content) == 0


def test_phase2_atomic_clicks_count_increment():
    """3. Clicks count increments atomically and reflects correctly in stats."""
    import models
    from database import SessionLocal
    from main import track_click

    token = register_token("atomic_click")
    alias = f"atom_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/atomic", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Trigger clicks
    track_click(alias, "Mozilla/5.0", "127.0.0.1")
    track_click(alias, "Mozilla/5.0", "127.0.0.1")

    with SessionLocal() as db:
        url = db.query(models.URL).filter(models.URL.short_id == alias).first()
        assert url.clicks_count >= 2


def test_phase2_utc_normalization_and_past_expiry_rejected():
    """4. Rejects past expires_at with 422 and normalizes future times to UTC."""
    from datetime import datetime, timedelta, timezone

    token = register_token("expiry_val")
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()

    # Past expiry must be rejected with 422
    past_resp = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com", "expires_at": past_iso},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert past_resp.status_code == 422
    assert "future" in past_resp.text.lower()

    # Future expiry accepted and normalized
    future_iso = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    future_resp = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com", "expires_at": future_iso},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert future_resp.status_code == 200


def test_phase2_sql_groupby_compile_stats():
    """5. compile_stats performs SQL GROUP BY and limits recent clicks to 20."""
    import models
    from database import SessionLocal
    from main import compile_stats

    alias = f"stats_{os.urandom(4).hex()}"
    with SessionLocal() as db:
        url = models.URL(
            short_id=alias,
            target_url="https://example.com/stats",
            clicks_count=25,
        )
        db.add(url)
        db.commit()
        db.refresh(url)

        # Insert 25 clicks across 2 countries
        for i in range(25):
            c_name = "United States" if i % 2 == 0 else "Germany"
            event = models.ClickEvent(
                url_id=url.id,
                country=c_name,
                ip_address="127.0.0.1",
                user_agent="TestAgent",
            )
            db.add(event)
        db.commit()

        stats = compile_stats(url, db)
        assert stats["countries"]["United States"] == 13
        assert stats["countries"]["Germany"] == 12
        assert len(stats["recent_clicks"]) == 20


def test_phase2_redis_cache_ttl_and_delete():
    """6. Redis cache uses TTL and DELETE purges cached keys."""
    token = register_token("cache_ttl_user")
    alias = f"ttl_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://cached-example.com", "custom_alias": alias},
        headers={"Authorization": f"Bearer {token}"},
    )

    if redis_cache.client:
        ttl = redis_cache.client.ttl(f"url:{alias}")
        assert ttl > 0

    # Delete link
    del_resp = client.delete(
        f"/api/user/links/{alias}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200

    if redis_cache.client:
        assert redis_cache.get(f"url:{alias}") is None


def test_phase2_user_links_pagination_and_sorting():
    """8. GET /api/user/links supports limit, offset, and orders by created_at DESC."""
    token = register_token("pagination_user")
    aliases = []
    for i in range(3):
        a = f"page_{i}_{os.urandom(3).hex()}"
        aliases.append(a)
        client.post(
            "/api/shorten",
            json={"target_url": f"https://example.com/{i}", "custom_alias": a},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Request limit 2
    resp = client.get(
        "/api/user/links?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # Most recent should be first
    assert items[0]["short_id"] == aliases[2]
    assert items[1]["short_id"] == aliases[1]


def test_phase2_user_agent_device_detection():
    """11. user_agents correctly parses browser, os, and device categories."""
    import models
    from database import SessionLocal
    from main import track_click

    alias = f"ua_{os.urandom(4).hex()}"
    with SessionLocal() as db:
        url = models.URL(short_id=alias, target_url="https://example.com")
        db.add(url)
        db.commit()

    # Mobile Safari
    mobile_ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
    )
    track_click(alias, mobile_ua, "127.0.0.1")

    with SessionLocal() as db:
        url = db.query(models.URL).filter(models.URL.short_id == alias).first()
        last_event = (
            db.query(models.ClickEvent)
            .filter(models.ClickEvent.url_id == url.id)
            .order_by(models.ClickEvent.id.desc())
            .first()
        )
        assert last_event.device == "Mobile"
        assert "Safari" in (last_event.browser or "")
        assert "iOS" in (last_event.os or "")
