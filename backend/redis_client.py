import os
import time

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    import redis
except ImportError:
    redis = None


class MockRedis:
    """Fallback in-memory caching and rate-limiting store if Redis is unavailable."""

    def __init__(self):
        self.data = {}
        self.expires = {}

    def _cleanup(self, key):
        if key in self.expires and time.time() > self.expires[key]:
            if key in self.data:
                del self.data[key]
            del self.expires[key]

    def get(self, key):
        self._cleanup(key)
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = str(value)
        if ex is not None:
            self.expires[key] = time.time() + ex
        return True

    def incr(self, key):
        self._cleanup(key)
        if key not in self.data:
            self.data[key] = "0"
        try:
            val = int(self.data[key]) + 1
            self.data[key] = str(val)
            return val
        except ValueError:
            return 1

    def expire(self, key, seconds):
        self._cleanup(key)
        if key in self.data:
            self.expires[key] = time.time() + seconds
            return True
        return False

    def ping(self):
        return True


class SafeRedisClient:
    """Wrapper that catches Redis errors and falls back gracefully to MockRedis."""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client = None
        self.fallback = MockRedis()
        self.last_reconnect_attempt = 0
        self.reconnect_cooldown = 10  # Try reconnecting at most once every 10 seconds
        self._init_client()

    def _init_client(self):
        self.last_reconnect_attempt = time.time()
        if redis is None:
            logger.warning("Redis package is not installed. Using MockRedis fallback.")
            self.client = None
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
                f"Could not connect to Redis at {self.redis_url} ({e}). Using MockRedis fallback."
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
                    f"Redis operation '{method_name}' failed: {e}. Falling back to MockRedis."
                )
                self.client = (
                    None  # Set client to None to trigger reconnect logic next time
                )
                self.last_reconnect_attempt = time.time()

        # Fallback execution
        method = getattr(self.fallback, method_name)
        return method(*args, **kwargs)

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
        return self.fallback.ping()


# Global Singleton Client instance
redis_cache = SafeRedisClient()
