"""Seed script to populate the database with sample data.

Run: python -m app.db.seed
"""

from __future__ import annotations
import asyncio
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.models import Candidate, CandidateProfile, CandidateSkill


SEED_DATA = {
    "candidate": {
        "full_name": "Alex Chen",
        "email": "alex.chen@example.com",
        "current_title": "Senior Full-Stack Engineer",
        "current_location": "Singapore",
    },
    "profile": {
        "summary": "Full-stack engineer with 6 years of experience building web applications, APIs, and data pipelines. Strong background in Python, TypeScript, and cloud infrastructure.",
        "years_experience": 6.0,
        "seniority_level": "senior",
        "preferred_roles": [
            "Full-Stack Engineer",
            "Backend Engineer",
            "Platform Engineer",
        ],
        "preferred_locations": ["Singapore", "Remote"],
        "remote_preference": "flexible",
    },
    "skills": [
        {"skill_name": "Python", "skill_level": "expert", "years_used": 6.0},
        {"skill_name": "FastAPI", "skill_level": "advanced", "years_used": 3.0},
        {"skill_name": "PostgreSQL", "skill_level": "advanced", "years_used": 5.0},
        {"skill_name": "Docker", "skill_level": "advanced", "years_used": 4.0},
        {"skill_name": "React", "skill_level": "intermediate", "years_used": 3.0},
        {"skill_name": "TypeScript", "skill_level": "intermediate", "years_used": 3.0},
        {"skill_name": "Git", "skill_level": "expert", "years_used": 6.0},
        {"skill_name": "AWS", "skill_level": "intermediate", "years_used": 3.0},
        {"skill_name": "Redis", "skill_level": "intermediate", "years_used": 2.0},
        {"skill_name": "CI/CD", "skill_level": "advanced", "years_used": 4.0},
        {"skill_name": "REST", "skill_level": "expert", "years_used": 6.0},
        {"skill_name": "SQL", "skill_level": "expert", "years_used": 6.0},
        {"skill_name": "Linux", "skill_level": "advanced", "years_used": 5.0},
        {"skill_name": "Testing", "skill_level": "advanced", "years_used": 5.0},
        {"skill_name": "Agile", "skill_level": "advanced", "years_used": 4.0},
        {
            "skill_name": "System design",
            "skill_level": "intermediate",
            "years_used": 3.0,
        },
        {
            "skill_name": "Observability",
            "skill_level": "intermediate",
            "years_used": 2.0,
        },
        {"skill_name": "Kubernetes", "skill_level": "intermediate", "years_used": 2.0},
    ],
}


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        # Check if already seeded
        from sqlalchemy import select

        existing = await session.execute(select(Candidate).limit(1))
        if existing.scalar_one_or_none():
            print("Database already seeded. Skipping.")
            return

        # Create candidate
        candidate = Candidate(**SEED_DATA["candidate"])
        session.add(candidate)
        await session.flush()

        # Create profile
        profile = CandidateProfile(
            candidate_id=candidate.id,
            **SEED_DATA["profile"],
        )
        session.add(profile)
        await session.flush()

        # Create skills
        for skill_data in SEED_DATA["skills"]:
            skill = CandidateSkill(
                candidate_profile_id=profile.id,
                **skill_data,
            )
            session.add(skill)

        await session.commit()
        print(f"Seeded candidate: {candidate.full_name} (id={candidate.id})")
        print(f"  Profile: {profile.seniority_level}, {profile.years_experience} years")
        print(f"  Skills: {len(SEED_DATA['skills'])}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
