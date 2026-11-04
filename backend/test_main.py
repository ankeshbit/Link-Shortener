import os
import sys
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ensure backend path is configured
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

    # 3. Try to access redirect URL, expect 302/303 redirect
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

    with patch("firebase_config._firebase_initialized", True), patch(
        "firebase_config.auth.verify_id_token", return_value=mock_claims
    ):
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
        user_short_ids = [link["short_id"] for link in links_resp.json()]
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

    with patch("firebase_config._firebase_initialized", True), patch(
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
    with patch("firebase_config._firebase_initialized", True), patch(
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


def test_metrics_endpoint_structure():
    """Asserts that /api/metrics returns the expected keys and types."""
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_redirects" in data
    assert "cache_hits" in data
    assert "cache_misses" in data
    assert "cache_hit_rate" in data
    assert isinstance(data["total_redirects"], int)
    assert isinstance(data["cache_hits"], int)
    assert isinstance(data["cache_misses"], int)
    assert isinstance(data["cache_hit_rate"], (int, float))


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_metrics_counter_increments():
    """Asserts that redirecting through short URLs increments metrics counters."""
    headers = {"Authorization": f"Bearer {register_token('metrics_user')}"}
    alias = f"metric_{os.urandom(4).hex()}"
    target = "https://example.com/metrics-test"

    # 1. Read baseline metrics
    before = client.get("/api/metrics").json()

    # 2. Shorten URL (which pre-populates the cache)
    create_resp = client.post(
        "/api/shorten",
        json={"target_url": target, "custom_alias": alias},
        headers=headers,
    )
    assert create_resp.status_code == 200

    # 3. Hit the redirect (cache hit)
    redir_resp = client.get(f"/{alias}", follow_redirects=False)
    assert redir_resp.status_code in [301, 302, 303, 307]

    after_hit = client.get("/api/metrics").json()
    if redis_cache.client:
        assert after_hit["total_redirects"] >= before["total_redirects"] + 1
        assert after_hit["cache_hits"] >= before["cache_hits"] + 1

    # 4. Invalidate cache and hit again (cache miss -> then cached)
    if redis_cache.client:
        redis_cache.client.delete(f"url:{alias}")

    redir_miss = client.get(f"/{alias}", follow_redirects=False)
    assert redir_miss.status_code in [301, 302, 303, 307]

    after_miss = client.get("/api/metrics").json()
    if redis_cache.client:
        assert after_miss["cache_misses"] >= after_hit["cache_misses"] + 1


def test_metrics_fail_open_on_redis_error():
    """Asserts that /api/metrics fails open and returns zero values if Redis is unreachable."""
    with patch("main.redis_cache.get", side_effect=Exception("Redis connection lost")):
        response = client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["cache_hits"] == 0
        assert data["cache_misses"] == 0
        assert data["cache_hit_rate"] == 0.0


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_redirect_sliding_window_rate_limit_enforced():
    """Verifies that sliding-window rate limiting returns 429 with Retry-After when limit is exceeded."""
    headers = {"Authorization": f"Bearer {register_token('rl_user_1')}"}
    alias = f"rl_enforce_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/rl-1", "custom_alias": alias},
        headers=headers,
    )

    client_ip = f"198.51.100.{os.urandom(1)[0]}"
    req_headers = {"X-Forwarded-For": client_ip}

    with patch.dict(
        os.environ, {"REDIRECT_RATE_LIMIT": "3", "REDIRECT_RATE_WINDOW": "60"}
    ):
        # 3 requests should succeed
        for _ in range(3):
            res = client.get(f"/{alias}", headers=req_headers, follow_redirects=False)
            assert res.status_code in [301, 302, 303, 307]

        # 4th request must be rejected with 429
        res_blocked = client.get(
            f"/{alias}", headers=req_headers, follow_redirects=False
        )
        assert res_blocked.status_code == 429
        assert "Retry-After" in res_blocked.headers
        retry_after = int(res_blocked.headers["Retry-After"])
        assert retry_after >= 1
        assert "Too many redirect requests" in res_blocked.json()["message"]


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_redirect_sliding_window_slides():
    """Verifies that older requests slide out of the sliding window, allowing subsequent requests."""
    headers = {"Authorization": f"Bearer {register_token('rl_user_2')}"}
    alias = f"rl_slide_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/rl-slide", "custom_alias": alias},
        headers=headers,
    )

    client_ip = f"198.51.100.{os.urandom(1)[0]}"
    req_headers = {"X-Forwarded-For": client_ip}

    # Window of 2 seconds, limit of 2 requests
    with patch.dict(
        os.environ, {"REDIRECT_RATE_LIMIT": "2", "REDIRECT_RATE_WINDOW": "2"}
    ):
        res1 = client.get(f"/{alias}", headers=req_headers, follow_redirects=False)
        res2 = client.get(f"/{alias}", headers=req_headers, follow_redirects=False)
        assert res1.status_code in [301, 302, 303, 307]
        assert res2.status_code in [301, 302, 303, 307]

        # 3rd request immediately fails
        res3 = client.get(f"/{alias}", headers=req_headers, follow_redirects=False)
        assert res3.status_code == 429

        # Wait for the 2-second window to slide past
        time.sleep(2.1)

        # 4th request must now succeed
        res4 = client.get(f"/{alias}", headers=req_headers, follow_redirects=False)
        assert res4.status_code in [301, 302, 303, 307]


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_redirect_rate_limit_per_client_ip():
    """Verifies rate limiting is isolated per client IP."""
    headers = {"Authorization": f"Bearer {register_token('rl_user_3')}"}
    alias = f"rl_ip_{os.urandom(4).hex()}"
    client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/rl-ip", "custom_alias": alias},
        headers=headers,
    )

    ip_a = f"198.51.100.1{os.urandom(1)[0]}"
    ip_b = f"198.51.100.2{os.urandom(1)[0]}"

    with patch.dict(
        os.environ, {"REDIRECT_RATE_LIMIT": "1", "REDIRECT_RATE_WINDOW": "60"}
    ):
        # IP A request 1 -> OK
        res_a1 = client.get(
            f"/{alias}", headers={"X-Forwarded-For": ip_a}, follow_redirects=False
        )
        assert res_a1.status_code in [301, 302, 303, 307]

        # IP A request 2 -> 429
        res_a2 = client.get(
            f"/{alias}", headers={"X-Forwarded-For": ip_a}, follow_redirects=False
        )
        assert res_a2.status_code == 429

        # IP B request 1 -> OK (not affected by IP A's quota)
        res_b1 = client.get(
            f"/{alias}", headers={"X-Forwarded-For": ip_b}, follow_redirects=False
        )
        assert res_b1.status_code in [301, 302, 303, 307]


def test_sliding_window_fail_open_on_redis_error():
    """Verifies that sliding window rate limiter safely fails open if Redis is down or errors."""
    with patch.object(redis_cache, "client") as mock_client:
        mock_client.eval.side_effect = Exception("Redis cluster unavailable")
        # Direct method call fails open
        allowed, rem, retry = redis_cache.sliding_window_rate_limit("test_key", 60, 5)
        assert allowed is True
        assert retry == 0

    # Also verify redirect handler fails open
    with patch("main.redis_cache.sliding_window_rate_limit", return_value=(True, 5, 0)):
        res = client.get("/nonexistent_alias_failopen", follow_redirects=False)
        # 404 because link doesn't exist, NOT 500 or 429
        assert res.status_code == 404


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_url_create_max_clicks_validation():
    """Asserts that max_clicks accepts >= 1 and rejects < 1."""
    headers = {"Authorization": f"Bearer {register_token('item3_val_user')}"}

    # 1. Valid max_clicks
    res_valid = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/mc-valid", "max_clicks": 10},
        headers=headers,
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["max_clicks"] == 10

    # 2. Invalid max_clicks (< 1)
    res_invalid = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/mc-invalid", "max_clicks": 0},
        headers=headers,
    )
    assert res_invalid.status_code == 422


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_patch_link_ownership_and_update():
    """Asserts that only the link owner can PATCH, and updates target_url, password, and active status."""
    token1 = register_token("owner_user_1")
    token2 = register_token("other_user_2")
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}

    alias = f"patch_own_{os.urandom(4).hex()}"
    create_res = client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/initial", "custom_alias": alias},
        headers=headers1,
    )
    assert create_res.status_code == 200

    # User 2 tries to PATCH user 1's link -> 403 Forbidden
    res_forbidden = client.patch(
        f"/api/user/links/{alias}",
        json={"target_url": "https://example.com/hijack"},
        headers=headers2,
    )
    assert res_forbidden.status_code == 403

    # User 1 successfully updates target_url, max_clicks, and sets password
    res_ok = client.patch(
        f"/api/user/links/{alias}",
        json={
            "target_url": "https://example.com/updated",
            "max_clicks": 50,
            "password": "NewSecretPassword123",
            "is_active": True,
        },
        headers=headers1,
    )
    assert res_ok.status_code == 200
    updated_data = res_ok.json()
    assert updated_data["target_url"] == "https://example.com/updated"
    assert updated_data["max_clicks"] == 50
    assert updated_data["has_password"] is True

    # User 1 clears password
    res_clear_pwd = client.patch(
        f"/api/user/links/{alias}",
        json={"clear_password": True},
        headers=headers1,
    )
    assert res_clear_pwd.status_code == 200
    assert res_clear_pwd.json()["has_password"] is False


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_patch_link_cache_invalidation_and_disable():
    """Verifies that PATCH invalidates cache and disabling refuses redirects on both cache and DB paths."""
    token = register_token("cache_inval_user")
    headers = {"Authorization": f"Bearer {token}"}
    alias = f"inval_{os.urandom(4).hex()}"

    # 1. Create link
    client.post(
        "/api/shorten",
        json={"target_url": "https://example.com/before-patch", "custom_alias": alias},
        headers=headers,
    )

    # 2. Redirect once to warm cache
    res1 = client.get(f"/{alias}", follow_redirects=False)
    assert res1.status_code in [301, 302, 303, 307]
    assert res1.headers["location"] == "https://example.com/before-patch"

    # 3. PATCH target_url
    patch_res = client.patch(
        f"/api/user/links/{alias}",
        json={"target_url": "https://example.com/after-patch"},
        headers=headers,
    )
    assert patch_res.status_code == 200

    # 4. Next redirect must route to after-patch (cache was invalidated)
    res2 = client.get(f"/{alias}", follow_redirects=False)
    assert res2.status_code in [301, 302, 303, 307]
    assert res2.headers["location"] == "https://example.com/after-patch"

    # 5. Disable link
    client.patch(
        f"/api/user/links/{alias}",
        json={"is_active": False},
        headers=headers,
    )

    # Cache path: redirect refused
    res_disabled_cache = client.get(f"/{alias}", follow_redirects=False)
    assert res_disabled_cache.status_code == 200
    assert (
        "Link Expired" in res_disabled_cache.text
        or "no longer active" in res_disabled_cache.text
    )

    # DB path (clear cache): redirect also refused
    if redis_cache.client:
        redis_cache.client.delete(f"url:{alias}")
    res_disabled_db = client.get(f"/{alias}", follow_redirects=False)
    assert res_disabled_db.status_code == 200
    assert (
        "Link Expired" in res_disabled_db.text
        or "no longer active" in res_disabled_db.text
    )


@pytest.mark.skipif(
    not database_alive(), reason="PostgreSQL test database not available"
)
def test_max_clicks_atomic_concurrency_cache_and_db():
    """Verifies that concurrent requests cannot exceed max_clicks on cache and DB paths."""
    import concurrent.futures

    token = register_token("concurrent_clicks_user")
    headers = {"Authorization": f"Bearer {token}"}
    alias = f"conc_{os.urandom(4).hex()}"

    # Create link with max_clicks = 4
    client.post(
        "/api/shorten",
        json={
            "target_url": "https://example.com/concurrent-limit",
            "custom_alias": alias,
            "max_clicks": 4,
        },
        headers=headers,
    )

    def do_redirect():
        # Separate client call
        res = client.get(f"/{alias}", follow_redirects=False)
        return res.status_code in [301, 302, 303, 307]

    # Hammer with 12 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda _: do_redirect(), range(12)))

    allowed_count = sum(results)
    assert allowed_count == 4, f"Expected exactly 4 allowed clicks, got {allowed_count}"

    # 13th request must also be refused
    res_over = client.get(f"/{alias}", follow_redirects=False)
    assert "no longer active" in res_over.text
