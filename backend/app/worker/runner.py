"""Out-of-process background worker for processing match jobs.

Run as: python -m app.worker.runner [--worker-id ID] [--poll-interval SECS]

Uses PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED for safe concurrent claiming.
Multiple workers can run simultaneously without duplicate processing.
"""

from __future__ import annotations
import asyncio
import argparse
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import get_settings
from app.models import MatchJob, CandidateProfile, CandidateSkill, Candidate
from app.services.scoring import (
    extract_skills,
    extract_seniority,
    extract_years_experience,
    extract_location_info,
    extract_title,
    compute_scores,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")


class MatchWorker:
    """Background worker that claims and processes match jobs from PostgreSQL."""

    def __init__(self, worker_id: str, settings=None):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.settings = settings or get_settings()
        self.engine = create_async_engine(
            self.settings.DATABASE_URL,
            echo=False,
            pool_size=5,
            pool_pre_ping=True,
        )
        self.Session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._running = True

    async def start(self, poll_interval: float = 2.0):
        """Main worker loop. Polls for jobs and processes them."""
        logger.info(
            f"[{self.worker_id}] Starting worker (poll_interval={poll_interval}s)"
        )

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)

        while self._running:
            try:
                processed = await self._poll_once()
                if not processed:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error(f"[{self.worker_id}] Poll error: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)

        logger.info(f"[{self.worker_id}] Worker stopped")

    def _shutdown(self):
        logger.info(f"[{self.worker_id}] Shutdown signal received")
        self._running = False

    async def _poll_once(self) -> bool:
        """Claim and process one job. Returns True if a job was processed."""
        async with self.Session() as session:
            job = await self._claim_job(session)
            if not job:
                return False

        # Process outside the claiming transaction
        await self._process_job(job)
        return True

    async def _claim_job(self, session: AsyncSession) -> MatchJob | None:
        """Atomically claim one pending job using FOR UPDATE SKIP LOCKED."""
        now = datetime.now(timezone.utc)

        # Use raw SQL for the atomic claim operation
        result = await session.execute(
            text("""
                UPDATE match_jobs
                SET status = 'processing',
                    locked_by = :worker_id,
                    locked_at = :now,
                    started_at = :now,
                    attempt_count = attempt_count + 1,
                    updated_at = :now
                WHERE id = (
                    SELECT id FROM match_jobs
                    WHERE status = 'pending'
                      AND attempt_count < max_attempts
                    ORDER BY queued_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id
            """),
            {"worker_id": self.worker_id, "now": now},
        )

        row = result.fetchone()
        if not row:
            return None

        await session.commit()

        # Fetch the full job
        job_result = await session.execute(
            select(MatchJob).where(MatchJob.id == row[0])
        )
        job = job_result.scalar_one()

        logger.info(
            f"[{self.worker_id}] Claimed job {job.id} "
            f"(attempt {job.attempt_count}/{job.max_attempts}, batch={job.batch_id})"
        )
        return job

    async def _process_job(self, job: MatchJob):
        """Process a claimed job: extract data and compute scores."""
        job_id = job.id
        start_time = datetime.now(timezone.utc)

        try:
            # Fetch candidate profile and skills
            async with self.Session() as session:
                profile_data = await self._load_candidate_profile(
                    session, job.candidate_id
                )

            # Extract job data
            text_content = job.source_value
            if job.source_type == "url":
                text_content = await self._fetch_url_content(job.source_value)

            extracted_skills = extract_skills(text_content)
            seniority = extract_seniority(text_content)
            years_exp = extract_years_experience(text_content)
            location_info = extract_location_info(text_content)
            title = extract_title(text_content)

            # Compute scores
            scores = compute_scores(
                job_skills=extracted_skills,
                job_seniority=seniority,
                job_years_exp=years_exp,
                job_location=location_info,
                candidate_skills=profile_data["skills"],
                candidate_years=profile_data["years_experience"],
                candidate_locations=profile_data["locations"],
                candidate_remote_pref=profile_data["remote_preference"],
                weight_skills=self.settings.WEIGHT_SKILLS,
                weight_experience=self.settings.WEIGHT_EXPERIENCE,
                weight_location=self.settings.WEIGHT_LOCATION,
            )

            # Persist results
            async with self.Session() as session:
                await session.execute(
                    update(MatchJob)
                    .where(MatchJob.id == job_id)
                    .values(
                        status="completed",
                        title=title,
                        score_overall=scores["score_overall"],
                        score_skills=scores["score_skills"],
                        score_experience=scores["score_experience"],
                        score_location=scores["score_location"],
                        matched_skills=scores["matched_skills"],
                        missing_skills=scores["missing_skills"],
                        recommendation=scores["recommendation"],
                        raw_extraction={
                            "skills": extracted_skills,
                            "seniority": seniority,
                            "years_experience": years_exp,
                            "location": location_info,
                        },
                        finished_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(
                f"[{self.worker_id}] Completed job {job_id} "
                f"(score={scores['score_overall']}, duration={duration:.2f}s)"
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            error_msg = str(e)[:500]
            logger.error(
                f"[{self.worker_id}] Failed job {job_id} "
                f"(duration={duration:.2f}s, error={error_msg})"
            )

            # Mark as failed
            async with self.Session() as session:
                await session.execute(
                    update(MatchJob)
                    .where(MatchJob.id == job_id)
                    .values(
                        status="failed",
                        error_code=type(e).__name__,
                        error_message=error_msg,
                        finished_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

    async def _load_candidate_profile(
        self, session: AsyncSession, candidate_id
    ) -> dict:
        """Load candidate profile data for scoring."""
        # Load profile
        profile_result = await session.execute(
            select(CandidateProfile).where(
                CandidateProfile.candidate_id == candidate_id
            )
        )
        profile = profile_result.scalar_one_or_none()

        # Load skills
        skills_result = await session.execute(
            select(CandidateSkill).where(
                CandidateSkill.candidate_profile_id == (profile.id if profile else None)
            )
        )
        skills = skills_result.scalars().all()

        return {
            "skills": [s.skill_name for s in skills],
            "years_experience": float(profile.years_experience)
            if profile and profile.years_experience
            else 5.0,
            "locations": profile.preferred_locations
            if profile and profile.preferred_locations
            else [],
            "remote_preference": profile.remote_preference
            if profile and profile.remote_preference
            else "flexible",
        }

    async def _fetch_url_content(self, url: str) -> str:
        """Fetch content from a URL. Returns text content."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                if "html" in content_type:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(resp.text, "html.parser")
                    # Remove script/style tags
                    for tag in soup(["script", "style"]):
                        tag.decompose()
                    return soup.get_text(separator="\n", strip=True)
                else:
                    return resp.text[:10000]
        except Exception as e:
            raise RuntimeError(f"Failed to fetch URL {url}: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Lazy Matcher Worker")
    parser.add_argument("--worker-id", default=None, help="Unique worker identifier")
    parser.add_argument(
        "--poll-interval", type=float, default=2.0, help="Poll interval in seconds"
    )
    args = parser.parse_args()

    settings = get_settings()
    worker_id = args.worker_id or f"worker-{os.getpid()}"
    worker = MatchWorker(worker_id=worker_id, settings=settings)
    await worker.start(poll_interval=args.poll_interval)


if __name__ == "__main__":
    asyncio.run(main())
