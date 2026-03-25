"""Pydantic schemas for API request/response validation."""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# --- Request schemas ---


class MatchItemInput(BaseModel):
    """Single job description or URL in a batch submission."""

    content: str = Field(
        ..., min_length=1, max_length=50000, description="Job description text or URL"
    )
    source_type: Optional[str] = Field(
        default=None,
        description="Explicit source type: 'text' or 'url'. Auto-detected if omitted.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Preferred LLM model: 'gemini' or 'openrouter'. Uses config default if omitted.",
    )


class MatchBatchRequest(BaseModel):
    """Batch submission request body."""

    items: list[MatchItemInput] = Field(..., min_length=1, max_length=10)

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[MatchItemInput]) -> list[MatchItemInput]:
        if len(v) > 10:
            raise ValueError("Maximum 10 items per batch")
        # Check for duplicates within the batch
        seen = set()
        for item in v:
            key = item.content.strip().lower()
            if key in seen:
                raise ValueError(f"Duplicate entry: '{item.content[:50]}...'")
            seen.add(key)
        return v


# --- Response schemas ---


class MatchJobResponse(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    candidate_id: uuid.UUID
    source_type: str
    source_value: str
    title: Optional[str] = None
    status: str
    attempt_count: int
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    score_overall: Optional[int] = None
    score_skills: Optional[int] = None
    score_experience: Optional[int] = None
    score_location: Optional[int] = None
    matched_skills: Optional[list[str]] = None
    missing_skills: Optional[list[str]] = None
    recommendation: Optional[str] = None
    years_experience: Optional[int] = None
    llm_model: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MatchBatchResponse(BaseModel):
    """Response after submitting a batch."""

    batch_id: uuid.UUID
    job_count: int
    jobs: list[MatchJobResponse]


class MatchJobListResponse(BaseModel):
    """Paginated list of match jobs."""

    items: list[MatchJobResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
