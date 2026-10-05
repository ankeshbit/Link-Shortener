import json
import os
from typing import Any, Optional

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import auth, credentials
from loguru import logger

load_dotenv()

_firebase_initialized = False


def initialize_firebase() -> bool:
    """
    Initializes the Firebase Admin SDK using environment-based credentials.
    Supports in order of priority:
    1. Individual environment variables (Render-friendly):
       - FIREBASE_PROJECT_ID
       - FIREBASE_CLIENT_EMAIL
       - FIREBASE_PRIVATE_KEY (escaped newlines supported)
    2. Raw service account JSON string:
       - FIREBASE_SERVICE_ACCOUNT_JSON
    3. Path to credentials file (Render Secret File or local):
       - FIREBASE_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS
    4. Project ID with Application Default Credentials:
       - FIREBASE_PROJECT_ID
    5. Default credentials fallback.
    """
    global _firebase_initialized
    if _firebase_initialized or firebase_admin._apps:
        _firebase_initialized = True
        return True

    # 1. Check for individual environment variables
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
    private_key = os.getenv("FIREBASE_PRIVATE_KEY")

    try:
        if project_id and client_email and private_key:
            clean_project_id = project_id.strip().strip("'\"")
            clean_client_email = client_email.strip().strip("'\"")
            # Replace literal escaped \n with actual newlines
            clean_private_key = (
                private_key.strip().strip("'\"").replace("\\n", "\n")
            )

            logger.info(
                f"Initializing Firebase Admin using individual credentials for project: {clean_project_id}."
            )
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": clean_project_id,
                "private_key": clean_private_key,
                "client_email": clean_client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            return True

        # 2. Check for monolithic service account JSON string
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if service_account_json and service_account_json.strip():
            logger.info("Initializing Firebase Admin with FIREBASE_SERVICE_ACCOUNT_JSON.")
            cred_dict = json.loads(service_account_json.strip())
            if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            return True

        # 3. Check for credentials file path
        credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        if credentials_path and os.path.exists(credentials_path):
            logger.info(
                f"Initializing Firebase Admin with credentials file at {credentials_path}."
            )
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            return True

        # 4. Fallback to Application Default Credentials with Project ID
        if project_id:
            clean_project_id = project_id.strip().strip("'\"")
            logger.info(
                f"Initializing Firebase Admin with project ID {clean_project_id} using default credentials."
            )
            firebase_admin.initialize_app(options={"projectId": clean_project_id})
            _firebase_initialized = True
            return True

        # 5. Default credentials fallback
        logger.info("Initializing Firebase Admin with ambient default credentials.")
        firebase_admin.initialize_app()
        _firebase_initialized = True
        return True
    except Exception as exc:
        logger.warning(
            f"Firebase Admin SDK initialization deferred: {type(exc).__name__}. "
            "Ensure FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, and FIREBASE_PRIVATE_KEY are set."
        )
        return False


def verify_firebase_id_token(token: str) -> Optional[dict[str, Any]]:
    """
    Cryptographically verifies a Firebase ID token using the Firebase Admin SDK.
    Returns a normalized dictionary containing:
    - uid: verified Firebase unique user ID
    - email: verified email address
    - name: user display name (if present)
    - picture: profile picture URL (if present)
    - email_verified: boolean verification status

    Never trusts frontend claims or unverified payloads.
    Logs only safe, non-sensitive diagnostic categories on failure.
    """
    if not token or not isinstance(token, str):
        return None

    if not _firebase_initialized and not firebase_admin._apps:
        if not initialize_firebase():
            logger.error(
                "Authentication failure: Firebase Admin is not initialized. "
                "Check FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, and FIREBASE_PRIVATE_KEY."
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
        logger.warning("Firebase ID token verification failed: token is expired.")
        return None
    except auth.RevokedIdTokenError:
        logger.warning("Firebase ID token verification failed: token has been revoked.")
        return None
    except auth.InvalidIdTokenError:
        logger.warning("Firebase ID token verification failed: invalid token signature or structure.")
        return None
    except auth.CertificateFetchError:
        logger.error("Firebase ID token verification failed: unable to fetch public key certificates.")
        return None
    except ValueError:
        logger.warning("Firebase ID token verification failed: malformed token or project ID mismatch.")
        return None
    except Exception as e:
        logger.error(f"Firebase ID token verification failed: unexpected error ({type(e).__name__}).")
        return None
