import logging
import time

try:
    import redis
except ImportError:
    redis = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockRedis:
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
        self.data[key] = value
        if ex is not None:
            self.expires[key] = time.time() + ex
        
    def incr(self, key):
        self._cleanup(key)
        if key not in self.data:
            self.data[key] = 0
        self.data[key] += 1
        return self.data[key]

    def expire(self, key, seconds):
        if key in self.data:
            self.expires[key] = time.time() + seconds

def get_redis_client():
    if redis is None:
        logger.warning("Redis package is not installed. Using MockRedis fallback for Caching/Rate Limiting.")
        return MockRedis()

    try:
        client = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5, retry_on_timeout=False)
        # Ping to check if Redis is alive
        client.ping()
        logger.info("Connected to Redis gracefully.")
        return client
    except Exception as e:
        logger.warning(f"Redis is not available ({e}). Using MockRedis fallback for Caching/Rate Limiting.")
        return MockRedis()

redis_cache = get_redis_client()
