"""Redis job notification service.

Uses Upstash Redis LPUSH/RPOP as a lightweight message queue.
API pushes job IDs when jobs are created; worker pops them for
immediate processing instead of waiting for the next DB poll.
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from app.services.cache import get_redis

logger = logging.getLogger(__name__)

QUEUE_KEY = "jobs:pending"


def notify_job(job_id: str) -> bool:
    """Push a job ID onto the pending queue. Returns True on success."""
    client = get_redis()
    if not client:
        return False
    try:
        client.lpush(QUEUE_KEY, job_id)
        logger.debug(f"Notified: {job_id}")
        return True
    except Exception as e:
        logger.warning(f"Redis notify failed: {e}")
        return False


def notify_jobs(job_ids: list[str]) -> bool:
    """Push multiple job IDs onto the pending queue in a single operation."""
    if not job_ids:
        return True
    client = get_redis()
    if not client:
        return False
    try:
        # upstash-redis doesn't have rpush_many, so pipeline or lpush loop
        for jid in job_ids:
            client.lpush(QUEUE_KEY, jid)
        logger.debug(f"Notified {len(job_ids)} jobs")
        return True
    except Exception as e:
        logger.warning(f"Redis notify failed: {e}")
        return False


def pop_pending_job(timeout: int = 1) -> Optional[str]:
    """Pop a single job ID from the queue. Returns None if empty.

    timeout parameter is for future BRPOP support; currently uses RPOP
    since upstash-redis REST doesn't support blocking operations.
    """
    client = get_redis()
    if not client:
        return None
    try:
        raw = client.rpop(QUEUE_KEY)
        if raw:
            return str(raw)
        return None
    except Exception as e:
        logger.debug(f"Redis pop error: {e}")
        return None


def queue_length() -> int:
    """Return the number of pending notifications."""
    client = get_redis()
    if not client:
        return 0
    try:
        return client.llen(QUEUE_KEY)
    except Exception:
        return 0
