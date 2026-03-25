"""Backend integration test: full match job lifecycle.

Tests: POST batch -> observe pending -> worker claims -> worker completes -> GET results.
"""

import os
import uuid
import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/lazy_matcher",
)

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.config import get_settings
from app.db.session import get_db
from app.models.candidate import Base, Candidate, CandidateProfile, CandidateSkill
from app.worker.runner import MatchWorker


@pytest.fixture()
async def db_session():
    """Create a fresh test database for each test function."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.close()

    # Reset tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed test candidate
    async with session_factory() as session:
        candidate = Candidate(
            full_name="Test Candidate",
            email="test@example.com",
            current_title="Test Engineer",
            current_location="Remote",
        )
        session.add(candidate)
        await session.flush()

        profile = CandidateProfile(
            candidate_id=candidate.id,
            summary="Test profile",
            years_experience=5.0,
            seniority_level="senior",
            preferred_roles=["Engineer"],
            preferred_locations=["Remote"],
            remote_preference="remote",
        )
        session.add(profile)
        await session.flush()

        for skill_name in ["Python", "FastAPI", "PostgreSQL", "Docker", "React"]:
            session.add(
                CandidateSkill(
                    candidate_profile_id=profile.id,
                    skill_name=skill_name,
                    skill_level="advanced",
                    years_used=3.0,
                )
            )
        await session.commit()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_lifecycle(db_session):
    """Test the complete match job lifecycle: submit -> pending -> processing -> completed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Submit a batch
        response = await client.post(
            "/api/v1/matches",
            json={
                "items": [
                    {
                        "content": "Senior Python Engineer — 5+ years, FastAPI, PostgreSQL, Docker"
                    },
                    {
                        "content": "Frontend Developer — React, TypeScript, CSS, 3+ years"
                    },
                ]
            },
        )
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data["job_count"] == 2
        assert len(data["jobs"]) == 2
        batch_id = data["batch_id"]

        # Check all jobs are pending
        for job in data["jobs"]:
            assert job["status"] == "pending"
            assert job["batch_id"] == batch_id

        job_ids = [j["id"] for j in data["jobs"]]

        # 2. Verify GET endpoint returns pending jobs
        response = await client.get(f"/api/v1/matches/{job_ids[0]}")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

        # 3. Run the worker to process jobs
        worker = MatchWorker(worker_id="test-worker-1", settings=get_settings())
        await worker._poll_once()  # Process first job
        await worker._poll_once()  # Process second job

        # 4. Verify jobs are completed
        response = await client.get(f"/api/v1/matches/{job_ids[0]}")
        assert response.status_code == 200
        job1 = response.json()
        assert job1["status"] == "completed"
        assert job1["score_overall"] is not None
        assert 0 <= job1["score_overall"] <= 100
        assert job1["score_skills"] is not None
        assert isinstance(job1["matched_skills"], list)
        assert isinstance(job1["missing_skills"], list)
        assert job1["recommendation"] is not None

        response = await client.get(f"/api/v1/matches/{job_ids[1]}")
        job2 = response.json()
        assert job2["status"] == "completed"

        # 5. Test list endpoint with pagination
        response = await client.get("/api/v1/matches?limit=10&offset=0")
        assert response.status_code == 200
        list_data = response.json()
        assert list_data["total"] >= 2
        assert len(list_data["items"]) >= 2

        # 6. Test list endpoint with status filter
        response = await client.get("/api/v1/matches?status=completed")
        assert response.status_code == 200
        completed_data = response.json()
        assert all(item["status"] == "completed" for item in completed_data["items"])

        # 7. Test pending filter returns 0 now
        response = await client.get("/api/v1/matches?status=pending")
        assert response.status_code == 200
        assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_validation_errors(db_session):
    """Test that invalid submissions return proper error responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty batch
        response = await client.post("/api/v1/matches", json={"items": []})
        assert response.status_code == 422

        # Too many items (>10)
        response = await client.post(
            "/api/v1/matches",
            json={"items": [{"content": f"Job {i}"} for i in range(11)]},
        )
        assert response.status_code == 422

        # Duplicate items
        response = await client.post(
            "/api/v1/matches",
            json={
                "items": [
                    {"content": "Same job description"},
                    {"content": "Same job description"},
                ]
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_not_found(db_session):
    """Test 404 for non-existent job."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/matches/{fake_id}")
        assert response.status_code == 404
