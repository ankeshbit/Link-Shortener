import os
import time

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    import redis
except ImportError:
    redis = None


class SafeRedisClient:
    """Redis cache client; PostgreSQL remains the source of truth."""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.client = None
        self.last_reconnect_attempt = 0
        self.reconnect_cooldown = 10  # Try reconnecting at most once every 10 seconds
        self._init_client()

    def _init_client(self):
        self.last_reconnect_attempt = time.time()
        if not self.redis_url:
            logger.warning("REDIS_URL is not configured; Redis features are disabled.")
            return
        if redis is None:
            logger.warning("Redis package is not installed; Redis features are disabled.")
            return

        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                retry_on_timeout=False,
            )
            # Verify connectivity
            self.client.ping()
            logger.info("Connected to Redis server successfully.")
        except Exception as e:
            logger.warning(
                f"Could not connect to configured Redis ({e}). Redis features are disabled."
            )
            self.client = None

    def _should_attempt_reconnect(self) -> bool:
        return (
            self.client is None
            and (time.time() - self.last_reconnect_attempt) > self.reconnect_cooldown
        )

    def _execute(self, method_name, *args, **kwargs):
        # Attempt background reconnect if cooling down period has elapsed
        if self._should_attempt_reconnect():
            logger.info("Attempting to reconnect to Redis...")
            self._init_client()

        if self.client:
            try:
                method = getattr(self.client, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Redis operation '{method_name}' failed: {e}."
                )
                self.client = (
                    None  # Set client to None to trigger reconnect logic next time
                )
                self.last_reconnect_attempt = time.time()

        return None

    def get(self, key):
        return self._execute("get", key)

    def set(self, key, value, ex=None):
        return self._execute("set", key, value, ex=ex)

    def incr(self, key):
        return self._execute("incr", key)

    def expire(self, key, seconds):
        return self._execute("expire", key, seconds)

    def ping(self) -> bool:
        if self._should_attempt_reconnect():
            self._init_client()
        if self.client:
            try:
                return self.client.ping()
            except Exception:
                self.client = None
                return False
        return False


# Global Singleton Client instance
redis_cache = SafeRedisClient()
