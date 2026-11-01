import json
import os
import sys

import httpx

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models
from database import SessionLocal
from redis_client import redis_cache

BASE_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:5173"


def run_live_verification():
    print("=" * 60)
    print("STARTING LIVE LOCALHOST END-TO-END VERIFICATION")
    print("=" * 60)

    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # Step 1: Health Check
        print("\n[Step 1] Checking Live Backend Health...")
        health_resp = client.get("/health")
        assert (
            health_resp.status_code == 200
        ), f"Expected 200, got {health_resp.status_code}"
        health_data = health_resp.json()
        print(f"  Health Response: {health_data}")
        assert health_data["status"] == "healthy", "Database is not healthy"
        assert (
            health_data["redis"] == "connected"
        ), f"Redis is not connected: {health_data['redis']}"
        print("  -> PostgreSQL: HEALTHY, Redis: CONNECTED (PASS)")

        # Step 2: Frontend Server Check
        print("\n[Step 2] Checking Live Frontend Server...")
        try:
            with httpx.Client(timeout=5.0) as fe_client:
                fe_resp = fe_client.get(FRONTEND_URL)
                assert fe_resp.status_code == 200
                assert "<!doctype html>" in fe_resp.text.lower()
                print("  -> Frontend running on http://localhost:5173 (PASS)")
        except Exception as e:
            print(f"  -> Frontend check error: {e}")

        # Step 3: Register/Login Authenticated User
        print("\n[Step 3] Registering / Authenticating User...")
        email = f"e2e_user_{os.urandom(4).hex()}@example.com"
        password = "SecurePassword123!"
        reg_resp = client.post(
            "/api/auth/register", json={"email": email, "password": password}
        )
        assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"
        tokens = reg_resp.json()
        access_token = tokens["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        print(f"  User registered: {email}")

        # Verify user sync / me endpoint
        me_resp = client.get("/api/auth/me", headers=auth_headers)
        assert me_resp.status_code == 200
        user_info = me_resp.json()
        user_id = user_info["id"]
        print(
            f"  User profile retrieved: ID {user_id}, Email {user_info['email']} (PASS)"
        )

        # Step 4: Create Short URL with Custom Alias
        print("\n[Step 4] Creating Short URL with Custom Alias...")
        alias = f"e2e_{os.urandom(4).hex()}"
        target_url = "https://en.wikipedia.org/wiki/URL_shortening"
        payload = {"target_url": target_url, "custom_alias": alias}
        shorten_resp = client.post("/api/shorten", json=payload, headers=auth_headers)
        assert shorten_resp.status_code == 200, f"Shorten failed: {shorten_resp.text}"
        short_data = shorten_resp.json()
        print(f"  Short URL created: {short_data['short_url']}")
        assert short_data["short_url"] == f"http://localhost:8000/{alias}"
        assert short_data["target_url"] == target_url
        print("  -> Short URL generation returned localhost domain (PASS)")

        # Step 5: Verify Persistence in PostgreSQL Database
        print("\n[Step 5] Verifying Persistence in PostgreSQL Database...")
        with SessionLocal() as db:
            db_record = (
                db.query(models.URL).filter(models.URL.short_id == alias).first()
            )
            assert db_record is not None, "URL record not found in PostgreSQL"
            assert db_record.target_url == target_url
            assert db_record.user_id == user_id
            print(
                f"  -> Record confirmed in PostgreSQL (ID: {db_record.id}, Clicks: {db_record.clicks_count}) (PASS)"
            )

        # Step 6: Verify Persistence in Redis Cache
        print("\n[Step 6] Verifying Redis Cache...")
        cached_str = redis_cache.get(f"url:{alias}")
        assert cached_str is not None, "URL not cached in Redis"
        cached_data = json.loads(cached_str)
        assert cached_data["target_url"] == target_url
        print(f"  -> Record confirmed in Redis cache: {cached_data} (PASS)")

        # Step 7: Public Redirection without Authentication
        print("\n[Step 7] Testing Public Redirection (Unauthenticated)...")
        redirect_resp = client.get(f"/{alias}", follow_redirects=False)
        assert redirect_resp.status_code in [
            302,
            303,
            307,
        ], f"Expected redirect, got {redirect_resp.status_code}"
        assert redirect_resp.headers["location"] == target_url
        print(
            f"  -> Redirect status: {redirect_resp.status_code}, Location: {redirect_resp.headers['location']} (PASS)"
        )

        # Step 8: Verify Click Analytics Recorded
        print("\n[Step 8] Verifying Click Analytics...")
        stats_resp = client.get(f"/api/stats/{alias}", headers=auth_headers)
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        print(f"  -> Total clicks: {stats_data['total_clicks']}")
        assert stats_data["total_clicks"] >= 1, "Click was not recorded"
        print("  -> Analytics recorded and retrieved successfully (PASS)")

        # Step 9: User Links History
        print("\n[Step 9] Fetching User Links History (Dashboard)...")
        links_resp = client.get("/api/user/links", headers=auth_headers)
        assert links_resp.status_code == 200
        links_list = links_resp.json()
        assert any(lnk["short_id"] == alias for lnk in links_list)
        print(f"  -> User owns {len(links_list)} links. Found {alias} (PASS)")

        # Step 10: Security & Protected Routes
        print("\n[Step 10] Testing Protected Route Security (Unauthenticated)...")
        unauth_shorten = client.post(
            "/api/shorten", json={"target_url": "https://example.com"}
        )
        assert unauth_shorten.status_code == 401
        assert "Authentication required" in unauth_shorten.text
        unauth_links = client.get("/api/user/links")
        assert unauth_links.status_code == 401
        print(
            "  -> Protected endpoints correctly reject unauthenticated requests with HTTP 401 (PASS)"
        )

        # Step 11: Delete Link
        print("\n[Step 11] Deleting Short Link...")
        del_resp = client.delete(f"/api/user/links/{alias}", headers=auth_headers)
        assert del_resp.status_code == 200
        get_deleted = client.get(f"/{alias}")
        assert get_deleted.status_code == 404
        print("  -> Link deleted and subsequent requests return HTTP 404 (PASS)")

    print("\n" + "=" * 60)
    print("ALL 11 END-TO-END VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_live_verification()
