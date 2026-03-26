"""Celery app configuration using Upstash Redis as broker."""

import logging

from celery import Celery
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

REDIS_URL = settings.REDIS_URL

if not REDIS_URL:
    logger.warning("REDIS_URL not set - Celery broker unavailable. Inline processing will be used.")
    celery_app = None
else:
    celery_app = Celery(
        "lazy_matcher",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        result_expires=3600,
    )

    celery_app.autodiscover_tasks(["app.worker"])
