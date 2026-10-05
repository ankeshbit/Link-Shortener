import json
import os
from typing import Any, Optional

import firebase_admin
from firebase_admin import auth, credentials
from loguru import logger

_firebase_initialized = False


def initialize_firebase() -> bool:
    """
    Initializes the Firebase Admin SDK using environment-based credentials.
    Supports:
    1. FIREBASE_SERVICE_ACCOUNT_JSON: Raw JSON string of the service account credentials.
    2. FIREBASE_CREDENTIALS_PATH: Path to service account JSON file (e.g., Render Secret File).
    3. GOOGLE_APPLICATION_CREDENTIALS: Standard Google application credentials path.
    4. FIREBASE_PROJECT_ID: Application Default Credentials with explicit project ID.
    5. Default credentials fallback.
    """
    global _firebase_initialized
    if _firebase_initialized or firebase_admin._apps:
        _firebase_initialized = True
        return True

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    project_id = os.getenv("FIREBASE_PROJECT_ID")

    try:
        if service_account_json and service_account_json.strip():
            logger.info("Initializing Firebase Admin with FIREBASE_SERVICE_ACCOUNT_JSON.")
            cred_dict = json.loads(service_account_json.strip())
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            return True

        if credentials_path and os.path.exists(credentials_path):
            logger.info(
                f"Initializing Firebase Admin with credentials file at {credentials_path}."
            )
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            return True

        # Fallback to Application Default Credentials
        if project_id:
            logger.info(
                f"Initializing Firebase Admin with project ID {project_id} using default credentials."
            )
            firebase_admin.initialize_app(options={"projectId": project_id})
            _firebase_initialized = True
            return True

        logger.info("Initializing Firebase Admin with default credentials.")
        firebase_admin.initialize_app()
        _firebase_initialized = True
        return True
    except Exception as exc:
        logger.warning(
            f"Firebase Admin SDK initialization deferred: {exc}. "
            "Backend will attempt to verify tokens if credentials are provided."
        )
        return False


def verify_firebase_id_token(token: str) -> Optional[dict[str, Any]]:
    """
    Verifies a Firebase ID token.
    Returns a normalized dictionary containing:
    - uid
    - email
    - name
    - picture
    - email_verified
    """
    if not token or not isinstance(token, str):
        return None

    if not _firebase_initialized and not firebase_admin._apps:
        if not initialize_firebase():
            logger.error(
                "Cannot verify Firebase ID token: Firebase Admin is not initialized. "
                "Ensure FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_PROJECT_ID is configured."
            )
            return None

    try:
        decoded = auth.verify_id_token(token, check_revoked=False)
        return {
            "uid": decoded.get("uid"),
            "email": decoded.get("email"),
            "name": decoded.get("name"),
            "picture": decoded.get("picture"),
            "email_verified": decoded.get("email_verified", False),
        }
    except auth.ExpiredIdTokenError:
        logger.warning("Firebase ID token is expired.")
        return None
    except auth.RevokedIdTokenError:
        logger.warning("Firebase ID token has been revoked.")
        return None
    except auth.InvalidIdTokenError as e:
        logger.warning(f"Invalid Firebase ID token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying Firebase ID token: {e}")
        return None
