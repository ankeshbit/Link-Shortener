import os
import time
import uuid

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    import redis
except ImportError:
    redis = None

SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window) + 1)
    return {1, limit - current_count - 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = math.ceil(window)
    if oldest and #oldest >= 2 then
        local oldest_time = tonumber(oldest[2])
        retry_after = math.max(1, math.ceil(oldest_time + window - now))
    end
    return {0, 0, retry_after}
end
"""

ATOMIC_CLICK_CHECK_LUA = """
local key = KEYS[1]
local max_clicks = tonumber(ARGV[1])
local initial_count = tonumber(ARGV[2])

local exists = redis.call('EXISTS', key)
if exists == 0 then
    redis.call('SET', key, initial_count)
end

local current = redis.call('INCR', key)
if current > max_clicks then
    return 0
else
    return 1
end
"""


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
            logger.warning(
                "Redis package is not installed; Redis features are disabled."
            )
            return

        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                protocol=2,
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
                logger.error(f"Redis operation '{method_name}' failed: {e}.")
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

    def delete(self, *keys):
        return self._execute("delete", *keys)

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

    def check_and_incr_clicks(
        self, short_id: str, max_clicks: int, initial_count: int = 0
    ) -> bool:
        """
        Atomically checks and increments click count for short_id in Redis.
        Returns True if click is allowed (within max_clicks), False if exceeded.
        Fails open (returns True) if Redis is down or unavailable.
        """
        if self._should_attempt_reconnect():
            self._init_client()

        if not self.client:
            return True

        key = f"url:{short_id}:clicks"
        try:
            res = self.client.eval(
                ATOMIC_CLICK_CHECK_LUA, 1, key, str(max_clicks), str(initial_count)
            )
            return bool(res == 1)
        except Exception as e:
            logger.warning(f"Atomic click check failed ({e}); failing open.")
            self.client = None
            self.last_reconnect_attempt = time.time()
            return True

    def sliding_window_rate_limit(
        self, key: str, window_seconds: float, limit: int
    ) -> tuple[bool, int, int]:
        """
        Sliding-window rate limiter using a Redis sorted set updated atomically via Lua.
        Returns: (allowed, remaining, retry_after)
        Fails open if Redis is down or encounters an error.
        """
        if self._should_attempt_reconnect():
            self._init_client()

        if not self.client:
            return True, limit, 0

        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"

        try:
            res = self.client.eval(
                SLIDING_WINDOW_LUA,
                1,
                key,
                str(now),
                str(window_seconds),
                str(limit),
                member,
            )
            if res and len(res) >= 3:
                return bool(res[0]), int(res[1]), int(res[2])
            return True, limit, 0
        except Exception as e:
            logger.warning(
                f"Sliding window rate limit operation failed ({e}); failing open."
            )
            self.client = None
            self.last_reconnect_attempt = time.time()
            return True, limit, 0


# Global Singleton Client instance
redis_cache = SafeRedisClient()
