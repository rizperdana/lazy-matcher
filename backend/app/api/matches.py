"""API routes for match endpoints."""

from __future__ import annotations
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import get_db
from app.models import MatchBatch, MatchJob, Candidate
from app.schemas import (
    MatchBatchRequest,
    MatchBatchResponse,
    MatchJobResponse,
    MatchJobListResponse,
)
from app.services.scoring import is_url, source_hash
from app.services.notifier import notify_jobs

router = APIRouter(prefix="/matches", tags=["matches"])


async def get_default_candidate(db: AsyncSession) -> uuid.UUID:
    """Get the default candidate ID. For simplicity, we use the first candidate."""
    result = await db.execute(select(Candidate.id).limit(1))
    candidate_id = result.scalar_one_or_none()
    if not candidate_id:
        raise HTTPException(
            status_code=500, detail="No candidate found. Run seed script first."
        )
    return candidate_id


def job_to_response(job: MatchJob) -> MatchJobResponse:
    """Convert MatchJob ORM to response schema."""
    return MatchJobResponse(
        id=job.id,
        batch_id=job.batch_id,
        candidate_id=job.candidate_id,
        source_type=job.source_type,
        source_value=job.source_value,
        title=job.title,
        status=job.status,
        attempt_count=job.attempt_count,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_code=job.error_code,
        error_message=job.error_message,
        score_overall=job.score_overall,
        score_skills=job.score_skills,
        score_experience=job.score_experience,
        score_location=job.score_location,
        matched_skills=job.matched_skills
        if isinstance(job.matched_skills, list)
        else [],
        missing_skills=job.missing_skills
        if isinstance(job.missing_skills, list)
        else [],
        recommendation=job.recommendation,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", response_model=MatchBatchResponse, status_code=201)
async def create_match_batch(
    body: MatchBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit a batch of 1-10 job descriptions for scoring.

    Returns immediately with pending jobs. Workers pick them up asynchronously.
    """
    candidate_id = await get_default_candidate(db)

    # Create batch
    batch = MatchBatch(
        candidate_id=candidate_id,
        request_count=len(body.items),
        status="pending",
    )
    db.add(batch)
    await db.flush()

    # Create jobs
    jobs: list[MatchJob] = []
    for item in body.items:
        content = item.content.strip()
        src_type = item.source_type or ("url" if is_url(content) else "text")
        s_hash = source_hash(content)

        job = MatchJob(
            batch_id=batch.id,
            candidate_id=candidate_id,
            source_type=src_type,
            source_value=content,
            source_hash=s_hash,
            title=content[:100] if src_type == "text" else content,
            status="pending",
        )
        db.add(job)
        jobs.append(job)

    await db.commit()

    # Refresh to get generated fields
    for job in jobs:
        await db.refresh(job)

    # Notify worker via Redis for immediate processing
    notify_jobs([str(j.id) for j in jobs])

    return MatchBatchResponse(
        batch_id=batch.id,
        job_count=len(jobs),
        jobs=[job_to_response(j) for j in jobs],
    )


@router.get("/{job_id}", response_model=MatchJobResponse)
async def get_match_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the current status and result for a single match job."""
    result = await db.execute(select(MatchJob).where(MatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job_to_response(job)


@router.get("", response_model=MatchJobListResponse)
async def list_match_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List match results, filterable by status with pagination."""
    candidate_id = await get_default_candidate(db)

    # Validate status filter
    valid_statuses = {"pending", "processing", "completed", "failed"}
    if status and status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    # Build query
    query = select(MatchJob).where(MatchJob.candidate_id == candidate_id)
    count_query = (
        select(func.count())
        .select_from(MatchJob)
        .where(MatchJob.candidate_id == candidate_id)
    )

    if status:
        query = query.where(MatchJob.status == status)
        count_query = count_query.where(MatchJob.status == status)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get paginated results, newest first
    query = query.order_by(MatchJob.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return MatchJobListResponse(
        items=[job_to_response(j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )
