"""Match batch and job ORM models."""

from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Text,
    SmallInteger,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.models.candidate import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MatchBatch(Base):
    __tablename__ = "match_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    jobs: Mapped[list[MatchJob]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class MatchJob(Base):
    __tablename__ = "match_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("match_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'text' or 'url'
    source_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)

    locked_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    score_overall: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_skills: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_experience: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_location: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    matched_skills: Mapped[dict | list | None] = mapped_column(JSONB, default=list)
    missing_skills: Mapped[dict | list | None] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    batch: Mapped[MatchBatch] = relationship(back_populates="jobs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_match_job_status",
        ),
        CheckConstraint(
            "score_overall IS NULL OR (score_overall >= 0 AND score_overall <= 100)",
            name="ck_score_overall_range",
        ),
        CheckConstraint(
            "score_skills IS NULL OR (score_skills >= 0 AND score_skills <= 100)",
            name="ck_score_skills_range",
        ),
        CheckConstraint(
            "score_experience IS NULL OR (score_experience >= 0 AND score_experience <= 100)",
            name="ck_score_exp_range",
        ),
        CheckConstraint(
            "score_location IS NULL OR (score_location >= 0 AND score_location <= 100)",
            name="ck_score_loc_range",
        ),
        Index("ix_match_jobs_candidate_status", "candidate_id", "status", "created_at"),
        Index("ix_match_jobs_queue", "status", "queued_at"),
        Index("ix_match_jobs_batch", "batch_id"),
        Index("ix_match_jobs_source_hash", "source_hash"),
    )
