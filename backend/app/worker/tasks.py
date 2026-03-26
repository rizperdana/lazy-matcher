"""Celery tasks for async job processing."""

import asyncio
import logging
import uuid

from app.core.celery import celery_app

logger = logging.getLogger("celery.worker")


@celery_app.task(
    bind=True, name="process_match_jobs", max_retries=2, default_retry_delay=10
)
def process_match_jobs(self, job_ids: list[str]):
    """Process match jobs asynchronously via Celery worker.

    Args:
        job_ids: List of job UUID strings to process.
    """
    from app.worker.runner import MatchWorker

    logger.info(f"Processing {len(job_ids)} jobs: {job_ids[:3]}...")

    async def _run():
        worker = MatchWorker(worker_id=f"celery-{self.request.id[:8]}")
        try:
            # Reset stuck jobs first
            from sqlalchemy import text
            from datetime import datetime, timezone, timedelta

            async with worker.Session() as session:
                await session.execute(
                    text("""
                        UPDATE match_jobs
                        SET status = 'pending', locked_by = NULL, locked_at = NULL
                        WHERE status = 'processing'
                          AND locked_at < :stale_time
                    """),
                    {"stale_time": datetime.now(timezone.utc) - timedelta(minutes=2)},
                )
                await session.commit()

            # Process pending jobs
            processed = await worker._poll_once()
            logger.info(f"Celery worker processed: {processed}")
            return processed
        except Exception as e:
            logger.error(f"Celery worker error: {e}", exc_info=True)
            raise
        finally:
            await worker.engine.dispose()

    # Run async code in sync Celery task
    try:
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        logger.error(f"Task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
