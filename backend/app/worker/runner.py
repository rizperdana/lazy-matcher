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
    source_hash,
)
from app.services.cache import get_cached_score, set_cached_score
from app.services.llm_scoring import get_llm_scorer
from app.services.notifier import pop_pending_job, queue_length

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
        """Main worker loop. Checks Redis for notifications, falls back to DB poll."""
        logger.info(
            f"[{self.worker_id}] Starting worker (poll_interval={poll_interval}s)"
        )

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown)

        while self._running:
            try:
                # 1. Try Redis notification queue first (immediate processing)
                processed_redis = await self._drain_redis_queue()
                # 2. Fall back to DB poll for any remaining jobs
                processed_db = await self._poll_once()
                if not processed_redis and not processed_db:
                    await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error(f"[{self.worker_id}] Poll error: {e}", exc_info=True)
                await asyncio.sleep(poll_interval)

        logger.info(f"[{self.worker_id}] Worker stopped")

    def _shutdown(self):
        logger.info(f"[{self.worker_id}] Shutdown signal received")
        self._running = False

    async def _drain_redis_queue(self) -> bool:
        """Check Redis for job notifications and process them. Returns True if any processed."""
        processed = False
        # Pop up to batch_size job IDs from Redis queue
        batch_size = (
            self.settings.LLM_BATCH_SIZE if self.settings.USE_LLM_SCORING else 1
        )
        job_ids = []
        for _ in range(batch_size):
            jid = pop_pending_job()
            if jid:
                job_ids.append(jid)
            else:
                break

        if not job_ids:
            return False

        # Fetch and claim the jobs from DB
        from uuid import UUID

        valid_ids = []
        for jid in job_ids:
            try:
                valid_ids.append(UUID(jid))
            except (ValueError, AttributeError):
                logger.warning(f"[{self.worker_id}] Invalid job ID from queue: {jid}")

        if not valid_ids:
            return False

        async with self.Session() as session:
            jobs = await self._claim_specific_jobs(session, valid_ids)

        if not jobs:
            return False

        if self.settings.USE_LLM_SCORING and len(jobs) > 1:
            await self._process_job_batch(jobs)
        else:
            for job in jobs:
                await self._process_job(job)

        return True

    async def _claim_specific_jobs(
        self, session: AsyncSession, job_ids: list[uuid.UUID]
    ) -> list[MatchJob]:
        """Claim specific pending jobs by ID using FOR UPDATE SKIP LOCKED."""
        now = datetime.now(timezone.utc)

        result = await session.execute(
            text("""
                UPDATE match_jobs
                SET status = 'processing',
                    locked_by = :worker_id,
                    locked_at = :now,
                    started_at = :now,
                    attempt_count = attempt_count + 1,
                    updated_at = :now
                WHERE id = ANY(:job_ids)
                  AND status = 'pending'
                  AND attempt_count < max_attempts
                RETURNING id
            """),
            {"worker_id": self.worker_id, "now": now, "job_ids": job_ids},
        )

        rows = result.fetchall()
        if not rows:
            return []

        await session.commit()

        claimed_ids = [row[0] for row in rows]
        job_result = await session.execute(
            select(MatchJob).where(MatchJob.id.in_(claimed_ids))
        )
        jobs = job_result.scalars().all()

        for job in jobs:
            logger.info(
                f"[{self.worker_id}] Claimed (redis) job {job.id} "
                f"(attempt {job.attempt_count}/{job.max_attempts})"
            )

        return list(jobs)

    async def _poll_once(self) -> bool:
        """Claim and process jobs. Returns True if any jobs were processed."""
        batch_size = (
            self.settings.LLM_BATCH_SIZE if self.settings.USE_LLM_SCORING else 1
        )

        async with self.Session() as session:
            jobs = await self._claim_jobs(session, batch_size)

        if not jobs:
            return False

        if self.settings.USE_LLM_SCORING and len(jobs) > 1:
            # Batch process with LLM
            await self._process_job_batch(jobs)
        else:
            # Process individually
            for job in jobs:
                await self._process_job(job)

        return True

    async def _claim_jobs(
        self, session: AsyncSession, batch_size: int
    ) -> list[MatchJob]:
        """Claim up to batch_size pending jobs using FOR UPDATE SKIP LOCKED."""
        now = datetime.now(timezone.utc)

        result = await session.execute(
            text("""
                UPDATE match_jobs
                SET status = 'processing',
                    locked_by = :worker_id,
                    locked_at = :now,
                    started_at = :now,
                    attempt_count = attempt_count + 1,
                    updated_at = :now
                WHERE id IN (
                    SELECT id FROM match_jobs
                    WHERE status = 'pending'
                      AND attempt_count < max_attempts
                    ORDER BY queued_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT :batch_size
                )
                RETURNING id
            """),
            {"worker_id": self.worker_id, "now": now, "batch_size": batch_size},
        )

        rows = result.fetchall()
        if not rows:
            return []

        await session.commit()

        # Fetch the full jobs
        job_ids = [row[0] for row in rows]
        job_result = await session.execute(
            select(MatchJob).where(MatchJob.id.in_(job_ids))
        )
        jobs = job_result.scalars().all()

        for job in jobs:
            logger.info(
                f"[{self.worker_id}] Claimed job {job.id} "
                f"(attempt {job.attempt_count}/{job.max_attempts})"
            )

        return list(jobs)

    async def _process_job_batch(self, jobs: list[MatchJob]):
        """Process a batch of jobs with LLM scoring."""
        from app.services.llm_scoring import get_llm_scorer

        scorer = get_llm_scorer()

        # Load candidate profiles and extract data for all jobs
        job_data = []
        profiles = []
        extracted_data = []

        for job in jobs:
            try:
                async with self.Session() as session:
                    profile_data = await self._load_candidate_profile(
                        session, job.candidate_id
                    )

                text_content = job.source_value
                if job.source_type == "url":
                    text_content = await self._fetch_url_content(job.source_value)

                extracted_skills = extract_skills(text_content)
                seniority = extract_seniority(text_content)
                years_exp = extract_years_experience(text_content)
                location_info = extract_location_info(text_content)
                title = extract_title(text_content)

                job_data.append(
                    {
                        "title": title,
                        "content": text_content,
                    }
                )
                profiles.append(profile_data)
                extracted_data.append(
                    {
                        "skills": extracted_skills,
                        "seniority": seniority,
                        "years_exp": years_exp,
                        "location": location_info,
                        "title": title,
                    }
                )
            except Exception as e:
                logger.error(f"[{self.worker_id}] Failed to prepare job {job.id}: {e}")

        if not job_data:
            return

        # Use the first profile for batch scoring (assume same candidate for batch)
        first_profile = profiles[0]

        # Check cache first for each job
        scores_list = []
        jobs_needing_scoring = []
        jobs_needing_scoring_indices = []

        for i, (job, ext_data) in enumerate(zip(jobs, extracted_data)):
            src_hash = source_hash(job.source_value)
            cached = get_cached_score(src_hash, str(job.candidate_id))
            if cached:
                scores_list.append(cached)
                logger.info(f"[{self.worker_id}] Cache hit for job {job.id}")
            else:
                scores_list.append(None)
                jobs_needing_scoring.append(job_data[i])
                jobs_needing_scoring_indices.append(i)

        # Score jobs that aren't cached
        if jobs_needing_scoring:
            try:
                llm_scores = await scorer.score_batch(
                    jobs=jobs_needing_scoring,
                    candidate_skills=first_profile["skills"],
                    candidate_years=first_profile["years_experience"],
                    candidate_locations=first_profile["locations"],
                    remote_preference=first_profile["remote_preference"],
                    weight_skills=self.settings.WEIGHT_SKILLS,
                    weight_experience=self.settings.WEIGHT_EXPERIENCE,
                    weight_location=self.settings.WEIGHT_LOCATION,
                )

                # Fill in scores
                for idx, score in zip(jobs_needing_scoring_indices, llm_scores):
                    scores_list[idx] = score
                    src_hash = source_hash(jobs[idx].source_value)
                    set_cached_score(src_hash, str(jobs[idx].candidate_id), score)
            except Exception as e:
                logger.error(f"[{self.worker_id}] Batch scoring failed: {e}")

        # Persist all results
        for job, scores, ext_data in zip(jobs, scores_list, extracted_data):
            if scores:
                await self._persist_job_result(job, scores, ext_data)
            else:
                # Mark as failed if no scores available
                await self._mark_job_failed(job, "No scores generated")

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

            # Check cache first (keyed by source hash + candidate)
            src_hash = source_hash(text_content)
            cached = get_cached_score(src_hash, str(job.candidate_id))

            if cached:
                scores = cached
                logger.info(f"[{self.worker_id}] Cache hit for job {job_id}")
            elif self.settings.USE_LLM_SCORING:
                # Try LLM scoring with deterministic fallback
                from app.services.llm_scoring import get_llm_scorer

                scorer = get_llm_scorer()
                scores = await scorer.score_single(
                    job_content=text_content,
                    job_title=title,
                    candidate_skills=profile_data["skills"],
                    candidate_years=profile_data["years_experience"],
                    candidate_locations=profile_data["locations"],
                    remote_preference=profile_data["remote_preference"],
                    weight_skills=self.settings.WEIGHT_SKILLS,
                    weight_experience=self.settings.WEIGHT_EXPERIENCE,
                    weight_location=self.settings.WEIGHT_LOCATION,
                )
                set_cached_score(src_hash, str(job.candidate_id), scores)
            else:
                # Pure deterministic scoring
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
                set_cached_score(src_hash, str(job.candidate_id), scores)

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
                        years_experience=int(years_exp) if years_exp else None,
                        llm_model=job.llm_model,
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

    async def _persist_job_result(self, job: MatchJob, scores: dict, ext_data: dict):
        """Persist scoring results for a job."""
        async with self.Session() as session:
            await session.execute(
                update(MatchJob)
                .where(MatchJob.id == job.id)
                .values(
                    status="completed",
                    title=ext_data["title"],
                    score_overall=scores["score_overall"],
                    score_skills=scores["score_skills"],
                    score_experience=scores["score_experience"],
                    score_location=scores["score_location"],
                    matched_skills=scores["matched_skills"],
                    missing_skills=scores["missing_skills"],
                    recommendation=scores["recommendation"],
                    raw_extraction={
                        "skills": ext_data["skills"],
                        "seniority": ext_data["seniority"],
                        "years_experience": ext_data["years_exp"],
                        "location": ext_data["location"],
                    },
                    years_experience=int(ext_data["years_exp"])
                    if ext_data["years_exp"]
                    else None,
                    llm_model=job.llm_model,
                    finished_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.info(
            f"[{self.worker_id}] Completed job {job.id} "
            f"(score={scores['score_overall']})"
        )

    async def _mark_job_failed(self, job: MatchJob, error_msg: str):
        """Mark a job as failed."""
        async with self.Session() as session:
            await session.execute(
                update(MatchJob)
                .where(MatchJob.id == job.id)
                .values(
                    status="failed",
                    error_code="ScoringError",
                    error_message=error_msg[:500],
                    finished_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.error(f"[{self.worker_id}] Failed job {job.id}: {error_msg}")

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
