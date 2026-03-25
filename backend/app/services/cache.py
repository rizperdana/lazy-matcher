"""Upstash Redis cache layer for scoring results.

Caches computed match scores keyed by source hash + candidate ID.
TTL: 1 hour (matches are deterministic, safe to cache).
Gracefully degrades if Upstash is unavailable.
"""

from __future__ import annotations
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client = None


def get_redis():
    """Lazy-init Upstash Redis client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client

    from app.core.config import get_settings
    from upstash_redis import Redis

    settings = get_settings()
    url = settings.UPSTASH_REDIS_URL
    token = settings.UPSTASH_REDIS_TOKEN

    if not url or not token:
        logger.info("Upstash Redis not configured — cache disabled")
        return None

    try:
        _client = Redis(url=url, token=token)
        # Quick connectivity check
        _client.ping()
        logger.info("Upstash Redis connected")
    except Exception as e:
        logger.warning(f"Upstash Redis unavailable: {e} — cache disabled")
        _client = None
    return _client


def cache_key(source_hash: str, candidate_id: str) -> str:
    """Generate cache key for a scoring result."""
    return f"score:{source_hash}:{candidate_id}"


def get_cached_score(source_hash: str, candidate_id: str) -> Optional[dict]:
    """Retrieve cached scoring result. Returns None on miss or error."""
    client = get_redis()
    if not client:
        return None
    try:
        key = cache_key(source_hash, candidate_id)
        data = client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug(f"Cache get error: {e}")
    return None


def set_cached_score(
    source_hash: str, candidate_id: str, scores: dict, ttl: int = 3600
) -> None:
    """Store scoring result in cache with TTL (default 1 hour)."""
    client = get_redis()
    if not client:
        return
    try:
        key = cache_key(source_hash, candidate_id)
        client.set(key, json.dumps(scores), ex=ttl)
    except Exception as e:
        logger.debug(f"Cache set error: {e}")


def cache_stats() -> dict[str, Any]:
    """Return basic cache health info."""
    client = get_redis()
    if not client:
        return {"status": "disabled", "connected": False}
    try:
        pong = client.ping()
        return {"status": "ok", "connected": pong is True}
    except Exception:
        return {"status": "error", "connected": False}
