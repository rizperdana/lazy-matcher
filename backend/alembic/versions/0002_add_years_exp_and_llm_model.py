"""Add years_experience and llm_model to match_jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-25
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "match_jobs",
        sa.Column("years_experience", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "match_jobs",
        sa.Column("llm_model", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("match_jobs", "llm_model")
    op.drop_column("match_jobs", "years_experience")
