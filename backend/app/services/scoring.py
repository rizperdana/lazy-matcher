"""Deterministic scoring service for matching jobs against candidate profiles.

Uses keyword extraction + rule-based scoring. No LLM dependency required.
Scoring dimensions: skills (50%), experience (30%), location (20%).
"""

from __future__ import annotations
import re
import hashlib
from urllib.parse import urlparse

# Common skill keywords for extraction (normalized to lowercase)
SKILL_KEYWORDS: list[str] = [
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "golang",
    "rust",
    "c++",
    "c#",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "elixir",
    "react",
    "react.js",
    "next.js",
    "nextjs",
    "vue",
    "vue.js",
    "angular",
    "svelte",
    "nuxt",
    "node.js",
    "nodejs",
    "express",
    "fastapi",
    "flask",
    "django",
    "rails",
    "spring",
    "fastify",
    "nest.js",
    "nestjs",
    "postgresql",
    "postgres",
    "mysql",
    "sqlite",
    "mongodb",
    "redis",
    "elasticsearch",
    "dynamodb",
    "cassandra",
    "docker",
    "kubernetes",
    "k8s",
    "terraform",
    "ansible",
    "helm",
    "aws",
    "gcp",
    "azure",
    "cloudflare",
    "vercel",
    "supabase",
    "firebase",
    "ci/cd",
    "github actions",
    "gitlab ci",
    "jenkins",
    "git",
    "github",
    "gitlab",
    "rest",
    "rest api",
    "graphql",
    "grpc",
    "websocket",
    "microservices",
    "serverless",
    "lambda",
    "sql",
    "nosql",
    "orm",
    "sqlalchemy",
    "prisma",
    "typeorm",
    "sequelize",
    "html",
    "css",
    "sass",
    "tailwind",
    "tailwindcss",
    "styled-components",
    "testing",
    "pytest",
    "jest",
    "vitest",
    "cypress",
    "playwright",
    "linux",
    "bash",
    "shell",
    "agile",
    "scrum",
    "kanban",
    "machine learning",
    "ml",
    "ai",
    "deep learning",
    "nlp",
    "data engineering",
    "etl",
    "airflow",
    "spark",
    "kafka",
    "observability",
    "monitoring",
    "prometheus",
    "grafana",
    "datadog",
    "system design",
    "architecture",
    "distributed systems",
    "design systems",
    "figma",
    "api design",
    "api gateway",
    "background jobs",
    "celery",
    "rq",
    "worker",
]

SENIORITY_SIGNALS: dict[str, int] = {
    "junior": 1,
    "entry": 1,
    "associate": 2,
    "mid": 3,
    "mid-level": 3,
    "intermediate": 3,
    "senior": 5,
    "sr": 5,
    "staff": 7,
    "principal": 8,
    "lead": 6,
    "architect": 8,
    "director": 9,
    "vp": 9,
    "head": 8,
}

EXPERIENCE_PATTERNS = [
    r"(\d+)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)",
    r"(\d+)\+?\s*years?\s*(?:of\s+)?(?:professional|industry)",
    r"minimum\s+(\d+)\s*years?",
    r"at\s+least\s+(\d+)\s*years?",
]


def is_url(text: str) -> bool:
    """Check if text looks like a URL."""
    try:
        parsed = urlparse(text.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def source_hash(text: str) -> str:
    """Generate a deterministic hash for deduplication."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def extract_skills(text: str) -> list[str]:
    """Extract matching skill keywords from text."""
    text_lower = text.lower()
    found: list[str] = []
    for skill in SKILL_KEYWORDS:
        # Use word boundary matching for short skills
        pattern = (
            r"\b" + re.escape(skill) + r"\b" if len(skill) <= 4 else re.escape(skill)
        )
        if re.search(pattern, text_lower):
            # Normalize the skill name
            normalized = skill.replace(".js", "").replace("js", "js")
            if normalized not in found:
                found.append(skill)
    return sorted(set(found))


def extract_seniority(text: str) -> int:
    """Extract seniority level from text. Returns years equivalent."""
    text_lower = text.lower()
    max_level = 0
    for keyword, level in SENIORITY_SIGNALS.items():
        if keyword in text_lower:
            max_level = max(max_level, level)
    return max_level


def extract_years_experience(text: str) -> int:
    """Extract explicit years of experience requirement."""
    text_lower = text.lower()
    years = []
    for pattern in EXPERIENCE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            years.append(int(match.group(1)))
    return max(years) if years else 0


def extract_location_info(text: str) -> dict:
    """Extract location/remote signals from text."""
    text_lower = text.lower()
    return {
        "remote": any(
            w in text_lower
            for w in ["remote", "work from home", "wfh", "distributed", "anywhere"]
        ),
        "hybrid": "hybrid" in text_lower,
        "onsite": any(
            w in text_lower for w in ["onsite", "on-site", "in-office", "in office"]
        ),
        "locations": [],  # Could extract city/country names
    }


def extract_title(text: str) -> str:
    """Extract a job title from the first line or first sentence."""
    lines = text.strip().split("\n")
    first_line = lines[0].strip()
    # If first line is short enough, use it as title
    if len(first_line) <= 120:
        # Clean up common prefixes
        title = re.sub(
            r"^(job\s*(title|position)\s*:\s*)", "", first_line, flags=re.IGNORECASE
        )
        return title.strip()[:100]
    # Otherwise use first sentence
    sentences = re.split(r"[.!?\n]", first_line)
    return sentences[0].strip()[:100] if sentences else "Untitled Position"


def compute_scores(
    job_skills: list[str],
    job_seniority: int,
    job_years_exp: int,
    job_location: dict,
    candidate_skills: list[str],
    candidate_years: float,
    candidate_locations: list[str],
    candidate_remote_pref: str,
    weight_skills: float = 0.5,
    weight_experience: float = 0.3,
    weight_location: float = 0.2,
) -> dict:
    """Compute dimension and overall scores.

    Returns dict with score_overall, score_skills, score_experience,
    score_location, matched_skills, missing_skills, recommendation.
    """
    # Normalize candidate skills to lowercase
    candidate_skills_lower = {s.lower() for s in candidate_skills}
    job_skills_lower = {s.lower() for s in job_skills}

    # Skills score
    if job_skills_lower:
        matched = job_skills_lower & candidate_skills_lower
        missing = job_skills_lower - candidate_skills_lower
        score_skills = int((len(matched) / len(job_skills_lower)) * 100)
    else:
        matched = set()
        missing = set()
        score_skills = 50  # neutral if no skills extracted

    # Experience score
    if job_years_exp > 0:
        ratio = min(candidate_years / job_years_exp, 1.5)
        score_experience = min(int(ratio * 100), 100)
    elif job_seniority > 0:
        # Map candidate years to seniority
        candidate_seniority = min(int(candidate_years / 2) + 1, 10)
        ratio = min(candidate_seniority / job_seniority, 1.5)
        score_experience = min(int(ratio * 100), 100)
    else:
        score_experience = 60  # neutral

    # Location score
    if job_location.get("remote"):
        if candidate_remote_pref in ("remote", "flexible", "any"):
            score_location = 100
        elif candidate_remote_pref == "hybrid":
            score_location = 80
        else:
            score_location = 50
    elif job_location.get("hybrid"):
        if candidate_remote_pref in ("hybrid", "flexible", "any"):
            score_location = 90
        elif candidate_remote_pref == "remote":
            score_location = 60
        else:
            score_location = 70
    else:
        score_location = 50  # conservative default

    # Overall score (weighted)
    score_overall = int(
        score_skills * weight_skills
        + score_experience * weight_experience
        + score_location * weight_location
    )
    score_overall = max(0, min(100, score_overall))

    # Recommendation
    recommendation = _generate_recommendation(
        score_overall,
        score_skills,
        score_experience,
        score_location,
        sorted(matched),
        sorted(missing),
        job_years_exp,
        candidate_years,
    )

    return {
        "score_overall": score_overall,
        "score_skills": score_skills,
        "score_experience": score_experience,
        "score_location": score_location,
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
        "recommendation": recommendation,
    }


def _generate_recommendation(
    overall: int,
    skills: int,
    experience: int,
    location: int,
    matched: list[str],
    missing: list[str],
    job_years: int,
    candidate_years: float,
) -> str:
    """Generate a human-readable recommendation string."""
    parts = []

    if overall >= 80:
        parts.append("Strong fit.")
    elif overall >= 60:
        parts.append("Good fit with some gaps.")
    elif overall >= 40:
        parts.append("Moderate fit. Consider upskilling.")
    else:
        parts.append("Significant gaps to address.")

    if matched:
        top = matched[:5]
        parts.append(f"Matched skills: {', '.join(top)}.")
    if missing:
        top = missing[:3]
        parts.append(f"Consider adding: {', '.join(top)} to your profile.")

    if skills < 50:
        parts.append("Focus on acquiring the missing technical skills.")
    if experience < 60 and job_years > 0:
        parts.append(f"Role requires {job_years}+ years; you have {candidate_years}.")

    return " ".join(parts)
