import redis
from src.settings import get_settings
from typing import Any, Optional
import json
import logging

logger = logging.getLogger(__name__)


class CacheClient:
    """Redis cache client for caching operations"""

    def __init__(self):
        settings = get_settings()
        self.client = redis.from_url(settings.redis_url, decode_responses=True)
        self.ttl = settings.redis_ttl
        logger.info(f"Connected to Redis at {settings.redis_url}")

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        try:
            ttl = ttl or self.ttl
            self.client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {e}")
            return False

    def clear(self) -> bool:
        """Clear all cache"""
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False

    def close(self):
        """Close Redis connection"""
        try:
            self.client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


_cache_client: Optional[CacheClient] = None


def get_cache_client() -> CacheClient:
    """Get or create cache client instance"""
    global _cache_client
    if _cache_client is None:
        _cache_client = CacheClient()
    return _cache_client
