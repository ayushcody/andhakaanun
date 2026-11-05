"""
Redis caching layer for analysis results.
Cache key = SHA256(case_text + location), TTL = configurable (default 1 hour).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("andhakaanun.cache")


class CacheService:
    """
    Redis-backed cache for analysis results.
    Falls back gracefully when Redis is unavailable.
    """

    def __init__(self, redis_client: Any | None, ttl_seconds: int = 3600):
        """
        Args:
            redis_client: Async Redis client (from app.state.redis).
            ttl_seconds: Cache TTL in seconds. Default 1 hour per PRD §3.3.
        """
        # Any: redis.asyncio client, or None when Redis is down (guarded by is_available).
        self._redis: Any = redis_client
        self._ttl = ttl_seconds

    @property
    def is_available(self) -> bool:
        return self._redis is not None

    @staticmethod
    def make_key(case_text: str, location: str = "") -> str:
        """
        Generate a deterministic cache key from case text + location.
        Uses SHA-256 hash per PRD §3.3.
        """
        raw = f"{case_text.strip().lower()}{location.strip().lower()}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"analysis:{digest}"

    async def get(self, case_text: str, location: str = "") -> dict[str, Any] | None:
        """
        Retrieve cached analysis result.

        Returns:
            Parsed JSON dict if cache hit, None if miss or unavailable.
        """
        if not self.is_available:
            return None

        key = self.make_key(case_text, location)
        try:
            cached = await self._redis.get(key)
            if cached:
                logger.info("Cache HIT: %s", key[:30])
                return json.loads(cached)
            logger.debug("Cache MISS: %s", key[:30])
            return None
        except Exception as e:
            logger.warning("Cache GET failed: %s", e)
            return None

    async def set(
        self,
        case_text: str,
        location: str,
        data: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """
        Store analysis result in cache.

        Returns:
            True if successfully cached, False otherwise.
        """
        if not self.is_available:
            return False

        key = self.make_key(case_text, location)
        try:
            serialized = json.dumps(data, default=str)
            await self._redis.set(key, serialized, ex=ttl or self._ttl)
            logger.info("Cache SET: %s (TTL=%ds)", key[:30], ttl or self._ttl)
            return True
        except Exception as e:
            logger.warning("Cache SET failed: %s", e)
            return False

    async def invalidate(self, case_text: str, location: str = "") -> bool:
        """Remove a cached entry."""
        if not self.is_available:
            return False

        key = self.make_key(case_text, location)
        try:
            await self._redis.delete(key)
            logger.info("Cache INVALIDATED: %s", key[:30])
            return True
        except Exception as e:
            logger.warning("Cache INVALIDATE failed: %s", e)
            return False

    async def ping(self) -> bool:
        """Check Redis connectivity."""
        if not self.is_available:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False
