"""
ByteLink URL Shortener - Regression Verification Script
Tests the 10 verified regressions against live PostgreSQL and Redis instances.
Prints explicit [PASS] or [FAIL] for each regression check.
"""

# ruff: noqa: E402

import concurrent.futures
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Set default test environment if not provided
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://bytelink:bytelink@127.0.0.1:5432/bytelink",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8000")
os.environ.setdefault("ENV", "development")
os.environ.setdefault(
    "JWT_SECRET", "reg_test_secret_key_at_least_32_characters_long_123456"
)
os.environ.setdefault("ALLOW_SHORT_JWT_SECRET", "false")
os.environ.setdefault("ENABLE_LEGACY_AUTH", "true")

import models
import security
from database import SessionLocal
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app, check_rate_limit
from redis_client import redis_cache


def log_result(check_name: str, passed: bool, detail: str = ""):
    status = "[PASS]" if passed else "[FAIL]"
    msg = f"{status} {check_name}"
    if detail and not passed:
        msg += f" - Reason: {detail}"
    print(msg)
    return passed


def get_test_auth_header(user_id: int) -> dict:
    token = security.create_access_token(data={"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def create_test_user(db) -> models.User:
    user = models.User(
        email=f"verify_reg_{os.urandom(6).hex()}@bytelink.co",
        firebase_uid=f"vuid_{os.urandom(8).hex()}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def cleanup_test_user(user_id: int):
    try:
        with SessionLocal() as db:
            db.query(models.User).filter_by(id=user_id).delete()
            db.commit()
    except Exception as e:
        print(f"Warning during cleanup: {e}", file=sys.stderr)


def reset_client_rate_limits():
    try:
        redis_cache.delete("rate_limit:127.0.0.1")
        redis_cache.delete("rate_limit:testclient")
    except Exception:
        pass


def run_checks() -> bool:
    all_passed = True
    print("=" * 70)
    print("Running ByteLink Regression Verification Suite against PostgreSQL & Redis")
    print("=" * 70)

    reset_client_rate_limits()

    with SessionLocal() as db:
        test_user = create_test_user(db)
    user_id = test_user.id
    auth_header = get_test_auth_header(user_id)

    with TestClient(app) as client:
        # -------------------------------------------------------------
        # Check 1: app refuses to start when JWT_SECRET is unset or < 32 chars
        # -------------------------------------------------------------
        check1_name = "app refuses to start when JWT_SECRET is unset or < 32 chars"
        try:
            # Subtest A: unset / empty
            cmd_unset = (
                "import sys, os; sys.path.insert(0, r'"
                + BACKEND_DIR
                + "'); os.environ['ALLOW_SHORT_JWT_SECRET'] = 'false'; "
                "os.environ['JWT_SECRET'] = ''; import security"
            )
            res_unset = subprocess.run(
                [sys.executable, "-c", cmd_unset],
                cwd=BACKEND_DIR,
                capture_output=True,
                text=True,
            )
            failed_unset = res_unset.returncode != 0 and (
                "JWT_SECRET" in (res_unset.stderr + res_unset.stdout)
                or "32 characters" in (res_unset.stderr + res_unset.stdout)
            )

            # Subtest B: short (< 32 chars)
            cmd_short = (
                "import sys, os; sys.path.insert(0, r'"
                + BACKEND_DIR
                + "'); os.environ['ALLOW_SHORT_JWT_SECRET'] = 'false'; "
                "os.environ['JWT_SECRET'] = 'short_secret'; import security"
            )
            res_short = subprocess.run(
                [sys.executable, "-c", cmd_short],
                cwd=BACKEND_DIR,
                capture_output=True,
                text=True,
            )
            failed_short = res_short.returncode != 0 and (
                "32 characters" in (res_short.stderr + res_short.stdout)
            )

            passed = failed_unset and failed_short
            detail = ""
            if not failed_unset:
                detail += (
                    f"Did not fail on unset JWT_SECRET (out: {res_unset.stderr}); "
                )
            if not failed_short:
                detail += f"Did not fail on short JWT_SECRET (out: {res_short.stderr});"
            if not log_result(check1_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check1_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 2: 30 concurrent clicks -> clicks_count == count(click_events)
        # -------------------------------------------------------------
        check2_name = "30 concurrent clicks -> clicks_count == count(click_events)"
        try:
            short_id_c30 = f"c30_{os.urandom(4).hex()}"
            with SessionLocal() as db:
                url_c30 = models.URL(
                    target_url="https://example.com/check2",
                    short_id=short_id_c30,
                    clicks_count=0,
                    user_id=user_id,
                )
                db.add(url_c30)
                db.commit()
                db.refresh(url_c30)
                url_c30_id = url_c30.id

            def hit_click():
                c = TestClient(app)
                return c.get(f"/{short_id_c30}", follow_redirects=False)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(hit_click) for _ in range(30)]
                for f in concurrent.futures.as_completed(futures):
                    f.result()

            # Allow background tasks to complete processing in database
            for _ in range(40):
                time.sleep(0.1)
                with SessionLocal() as db:
                    u = db.query(models.URL).filter_by(id=url_c30_id).first()
                    ev_count = (
                        db.query(models.ClickEvent).filter_by(url_id=url_c30_id).count()
                    )
                    if u.clicks_count == 30 and ev_count == 30:
                        break

            with SessionLocal() as db:
                u = db.query(models.URL).filter_by(id=url_c30_id).first()
                ev_count = (
                    db.query(models.ClickEvent).filter_by(url_id=url_c30_id).count()
                )
                passed = u.clicks_count == 30 and ev_count == 30
                detail = f"clicks_count={u.clicks_count}, events={ev_count}"
                if not log_result(check2_name, passed, detail):
                    all_passed = False
        except Exception as e:
            if not log_result(check2_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 3: rate limit returns 429
        # -------------------------------------------------------------
        check3_name = "rate limit returns 429"
        try:
            # Test check_rate_limit re-raises 429
            unique_rl_key = f"rate_limit:verify:{os.urandom(6).hex()}"
            limit_hit = False
            for _ in range(5):
                try:
                    check_rate_limit(unique_rl_key, limit=2, window=10)
                except HTTPException as he:
                    if he.status_code == 429:
                        limit_hit = True
                        break

            passed = limit_hit
            if not log_result(check3_name, passed, "429 status code was not raised"):
                all_passed = False
        except Exception as e:
            if not log_result(check3_name, False, str(e)):
                all_passed = False
        finally:
            reset_client_rate_limits()

        # -------------------------------------------------------------
        # Check 4: XSS payload in alias returns 422
        # -------------------------------------------------------------
        check4_name = (
            'XSS payload in alias ("><img src=x onerror=alert(1)>") returns 422'
        )
        try:
            reset_client_rate_limits()
            res_xss = client.post(
                "/api/shorten",
                headers=auth_header,
                json={
                    "target_url": "https://example.com",
                    "custom_alias": '"><img src=x onerror=alert(1)>',
                },
            )
            passed = res_xss.status_code == 422
            detail = f"status={res_xss.status_code}, body={res_xss.text}"
            if not log_result(check4_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check4_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 5: POST {"target_url": "ftp://x.com"} returns 422, not 500
        # -------------------------------------------------------------
        check5_name = 'POST {"target_url": "ftp://x.com"} returns 422, not 500'
        try:
            reset_client_rate_limits()
            res_ftp = client.post(
                "/api/shorten",
                headers=auth_header,
                json={"target_url": "ftp://x.com"},
            )
            passed = res_ftp.status_code == 422
            detail = f"status={res_ftp.status_code}, body={res_ftp.text}"
            if not log_result(check5_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check5_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 6: unverified email on firebase token does not link to existing legacy account
        # -------------------------------------------------------------
        check6_name = "unverified email on firebase token does not link to existing legacy account"
        try:
            legacy_email = f"leg_{os.urandom(4).hex()}@example.com"
            with SessionLocal() as db:
                leg_user = models.User(
                    email=legacy_email,
                    hashed_password=security.get_password_hash("legacy_pw_123"),
                )
                db.add(leg_user)
                db.commit()
                db.refresh(leg_user)
                leg_user_id = leg_user.id

            unverified_fb_info = {
                "email": legacy_email,
                "email_verified": False,
                "uid": f"unverified_fb_uid_{os.urandom(4).hex()}",
            }
            raised_401 = False
            with SessionLocal() as db:
                try:
                    security.get_or_create_user_from_firebase(db, unverified_fb_info)
                except HTTPException as he:
                    if he.status_code in (401, 409):
                        raised_401 = True

                # Verify user was not linked
                reloaded = db.query(models.User).filter_by(id=leg_user_id).first()
                not_linked = reloaded.firebase_uid is None

            passed = raised_401 and not_linked
            detail = f"raised_401={raised_401}, not_linked={not_linked}"
            if not log_result(check6_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check6_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 7: 100-char account password hashes and registers without 500
        # -------------------------------------------------------------
        check7_name = "100-char account password hashes and registers without 500"
        try:
            reset_client_rate_limits()
            long_pw = "K" * 100
            long_email = f"p100_{os.urandom(4).hex()}@bytelink.co"
            res_reg = client.post(
                "/api/auth/register",
                json={"email": long_email, "password": long_pw},
            )
            passed = res_reg.status_code == 201
            detail = f"status={res_reg.status_code}, body={res_reg.text}"
            if not log_result(check7_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check7_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 8: HEAD request on short link returns redirect/200, not 405
        # -------------------------------------------------------------
        check8_name = "HEAD request on short link returns redirect/200, not 405"
        try:
            short_head = f"head_{os.urandom(4).hex()}"
            with SessionLocal() as db:
                url_head = models.URL(
                    target_url="https://example.com/head-target",
                    short_id=short_head,
                    clicks_count=0,
                    user_id=user_id,
                )
                db.add(url_head)
                db.commit()

            res_head = client.head(f"/{short_head}", follow_redirects=False)
            passed = res_head.status_code in (301, 302, 307, 308, 200)
            detail = f"status={res_head.status_code}"
            if not log_result(check8_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check8_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 9: expiry works for +05:30 and -08:00 offsets; past expires_at returns 422
        # -------------------------------------------------------------
        check9_name = (
            "expiry works for +05:30 and -08:00 offsets; past expires_at returns 422"
        )
        try:
            reset_client_rate_limits()
            # +05:30 in future
            future_ist = (
                (datetime.now(timezone.utc) + timedelta(days=2))
                .astimezone(timezone(timedelta(hours=5, minutes=30)))
                .isoformat()
            )
            res_ist = client.post(
                "/api/shorten",
                headers=auth_header,
                json={
                    "target_url": "https://example.com/ist",
                    "expires_at": future_ist,
                },
            )

            # -08:00 in future
            future_pst = (
                (datetime.now(timezone.utc) + timedelta(days=2))
                .astimezone(timezone(timedelta(hours=-8)))
                .isoformat()
            )
            res_pst = client.post(
                "/api/shorten",
                headers=auth_header,
                json={
                    "target_url": "https://example.com/pst",
                    "expires_at": future_pst,
                },
            )

            # Past date
            past_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            res_past = client.post(
                "/api/shorten",
                headers=auth_header,
                json={
                    "target_url": "https://example.com/past",
                    "expires_at": past_date,
                },
            )

            passed = (
                res_ist.status_code == 200
                and res_pst.status_code == 200
                and res_past.status_code == 422
            )
            detail = (
                f"ist_status={res_ist.status_code}, "
                f"pst_status={res_pst.status_code}, "
                f"past_status={res_past.status_code}"
            )
            if not log_result(check9_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check9_name, False, str(e)):
                all_passed = False

        # -------------------------------------------------------------
        # Check 10: recent_clicks is newest-first and capped at 20
        # -------------------------------------------------------------
        check10_name = "recent_clicks is newest-first and capped at 20"
        try:
            short_rec = f"rec_{os.urandom(4).hex()}"
            with SessionLocal() as db:
                url_rec = models.URL(
                    target_url="https://example.com/recent",
                    short_id=short_rec,
                    clicks_count=25,
                    user_id=user_id,
                )
                db.add(url_rec)
                db.commit()
                db.refresh(url_rec)
                url_rec_id = url_rec.id

                base_time = datetime.now(timezone.utc)
                for i in range(25):
                    ev = models.ClickEvent(
                        url_id=url_rec_id,
                        ip_address="1.1.1.1",
                        country="United States",
                        city="Ashburn",
                        device="Desktop",
                        browser="Chrome",
                        os="Windows",
                        user_agent="Mozilla/5.0",
                        clicked_at=base_time - timedelta(minutes=25 - i),
                    )
                    db.add(ev)
                db.commit()

            res_analytics = client.get(
                f"/api/stats/{short_rec}",
                headers=auth_header,
            )
            data = res_analytics.json()
            recent = data.get("recent_clicks", [])

            is_capped_at_20 = len(recent) == 20
            # Parse timestamps from 'time' key and verify newest-first
            timestamps = [
                datetime.fromisoformat(r["time"].replace("Z", "+00:00"))
                for r in recent
                if r.get("time")
            ]
            is_newest_first = len(timestamps) == 20 and all(
                timestamps[i] >= timestamps[i + 1] for i in range(len(timestamps) - 1)
            )

            passed = (
                res_analytics.status_code == 200 and is_capped_at_20 and is_newest_first
            )
            detail = f"count={len(recent)}, newest_first={is_newest_first}"
            if not log_result(check10_name, passed, detail):
                all_passed = False
        except Exception as e:
            if not log_result(check10_name, False, str(e)):
                all_passed = False

    # Clean up test user and cascade
    cleanup_test_user(user_id)
    reset_client_rate_limits()

    print("=" * 70)
    if all_passed:
        print("ALL 10 REGRESSION CHECKS PASSED [PASS]")
        return True
    else:
        print("SOME REGRESSION CHECKS FAILED [FAIL]")
        return False


if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
