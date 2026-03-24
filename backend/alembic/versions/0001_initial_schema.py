"""Initial schema: candidates, profiles, skills, batches, jobs

Revision ID: 0001
Revises:
Create Date: 2026-03-24
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- candidates ---
    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True, unique=True),
        sa.Column("current_title", sa.Text(), nullable=True),
        sa.Column("current_location", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # --- candidate_profiles ---
    op.create_table(
        "candidate_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Numeric(4, 1), nullable=True),
        sa.Column("seniority_level", sa.Text(), nullable=True),
        sa.Column("preferred_roles", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("preferred_locations", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("remote_preference", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # --- candidate_skills ---
    op.create_table(
        "candidate_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("skill_level", sa.Text(), nullable=True),
        sa.Column("years_used", sa.Numeric(4, 1), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "candidate_profile_id", "skill_name", name="uq_profile_skill"
        ),
    )

    # --- match_batches ---
    op.create_table(
        "match_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "request_count", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # --- match_jobs ---
    op.create_table(
        "match_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "attempt_count", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "max_attempts", sa.SmallInteger(), nullable=False, server_default="3"
        ),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("score_overall", sa.SmallInteger(), nullable=True),
        sa.Column("score_skills", sa.SmallInteger(), nullable=True),
        sa.Column("score_experience", sa.SmallInteger(), nullable=True),
        sa.Column("score_location", sa.SmallInteger(), nullable=True),
        sa.Column("matched_skills", postgresql.JSONB(), server_default="[]"),
        sa.Column("missing_skills", postgresql.JSONB(), server_default="[]"),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("raw_extraction", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        # Constraints
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_match_job_status",
        ),
        sa.CheckConstraint(
            "score_overall IS NULL OR (score_overall >= 0 AND score_overall <= 100)",
            name="ck_score_overall_range",
        ),
        sa.CheckConstraint(
            "score_skills IS NULL OR (score_skills >= 0 AND score_skills <= 100)",
            name="ck_score_skills_range",
        ),
        sa.CheckConstraint(
            "score_experience IS NULL OR (score_experience >= 0 AND score_experience <= 100)",
            name="ck_score_exp_range",
        ),
        sa.CheckConstraint(
            "score_location IS NULL OR (score_location >= 0 AND score_location <= 100)",
            name="ck_score_loc_range",
        ),
    )

    # --- Indexes ---
    op.create_index(
        "ix_match_jobs_candidate_status",
        "match_jobs",
        ["candidate_id", "status", "created_at"],
    )
    op.create_index("ix_match_jobs_queue", "match_jobs", ["status", "queued_at"])
    op.create_index("ix_match_jobs_batch", "match_jobs", ["batch_id"])
    op.create_index("ix_match_jobs_source_hash", "match_jobs", ["source_hash"])


def downgrade() -> None:
    op.drop_table("match_jobs")
    op.drop_table("match_batches")
    op.drop_table("candidate_skills")
    op.drop_table("candidate_profiles")
    op.drop_table("candidates")
