"""LLM-based scoring service for matching jobs against candidate profiles.

Uses Gemini as primary LLM with OpenRouter as fallback.
Supports batch processing for token efficiency.
Falls back to deterministic scoring on any LLM failure.
Uses HTTP APIs directly (no heavy SDK dependencies).
"""

from __future__ import annotations
import json
import logging
import httpx
from typing import Any

from app.core.config import get_settings
from app.services.scoring import (
    compute_scores,
    extract_skills,
    extract_seniority,
    extract_years_experience,
    extract_location_info,
)

logger = logging.getLogger("llm_scoring")

# Prompt template for LLM scoring
SCORING_PROMPT = """You are a job matching expert. Score how well a candidate matches each job posting.

CANDIDATE PROFILE:
Skills: {candidate_skills}
Years of experience: {candidate_years}
Preferred locations: {candidate_locations}
Remote preference: {remote_preference}

JOB POSTINGS (batch):
{job_posts}

INSTRUCTIONS:
For each job posting, provide a JSON object with:
- job_index: The job index (0-based)
- score_overall: Overall match score 0-100
- score_skills: Skill match percentage 0-100
- score_experience: Experience match percentage 0-100
- score_location: Location match percentage 0-100
- matched_skills: List of skills the candidate has that match the job
- missing_skills: List of skills the job requires that the candidate lacks
- recommendation: Brief recommendation (1-2 sentences)

Respond with a JSON array containing one object per job posting.
Be concise. Use the exact field names specified."""


class LLMScorer:
    """LLM-based scoring with Gemini primary and OpenRouter fallback."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        return self._client

    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API via REST."""
        client = self._get_client()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.GEMINI_MODEL}:generateContent?key={self.settings.GEMINI_AI_KEY}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_openrouter(self, prompt: str) -> str:
        """Call OpenRouter API (OpenAI-compatible)."""
        client = self._get_client()
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.OPENROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _parse_llm_response(self, text: str) -> list[dict[str, Any]]:
        """Parse LLM JSON response, handling markdown fences."""
        try:
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            if not isinstance(result, list):
                result = [result]
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return []

    def _build_batch_prompt(
        self,
        jobs: list[dict[str, Any]],
        candidate_skills: list[str],
        candidate_years: float,
        candidate_locations: list[str],
        remote_preference: str,
    ) -> str:
        """Build the batch scoring prompt."""
        job_posts = []
        for i, job in enumerate(jobs):
            title = job.get("title", "Untitled Position")
            content = job.get("content", "")[:2000]
            job_posts.append(f"JOB {i}: {title}\n{content}")

        return SCORING_PROMPT.format(
            candidate_skills=", ".join(candidate_skills[:30]),
            candidate_years=candidate_years,
            candidate_locations=", ".join(candidate_locations[:5]),
            remote_preference=remote_preference,
            job_posts="\n\n---\n\n".join(job_posts),
        )

    def _validate_score_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Validate and clamp LLM scoring result."""
        return {
            "score_overall": max(0, min(100, int(result.get("score_overall", 50)))),
            "score_skills": max(0, min(100, int(result.get("score_skills", 50)))),
            "score_experience": max(
                0, min(100, int(result.get("score_experience", 50)))
            ),
            "score_location": max(0, min(100, int(result.get("score_location", 50)))),
            "matched_skills": list(result.get("matched_skills", [])),
            "missing_skills": list(result.get("missing_skills", [])),
            "recommendation": str(result.get("recommendation", "No recommendation")),
        }

    async def score_batch(
        self,
        jobs: list[dict[str, Any]],
        candidate_skills: list[str],
        candidate_years: float,
        candidate_locations: list[str],
        remote_preference: str,
        weight_skills: float = 0.5,
        weight_experience: float = 0.3,
        weight_location: float = 0.2,
    ) -> list[dict[str, Any]]:
        """Score a batch of jobs against a candidate profile.

        Tries Gemini first, then OpenRouter, then deterministic fallback.
        """
        if not jobs:
            return []

        prompt = self._build_batch_prompt(
            jobs,
            candidate_skills,
            candidate_years,
            candidate_locations,
            remote_preference,
        )

        # Try Gemini first
        try:
            logger.info(f"Trying Gemini for {len(jobs)} jobs")
            response_text = await self._call_gemini(prompt)
            results = self._parse_llm_response(response_text)
            if results and len(results) == len(jobs):
                logger.info(f"Gemini returned valid results for {len(jobs)} jobs")
                return [self._validate_score_result(r) for r in results]
            logger.warning(
                f"Gemini returned {len(results)} results, expected {len(jobs)}"
            )
        except Exception as e:
            logger.error(f"Gemini scoring failed: {e}")

        # Try OpenRouter fallback
        try:
            logger.info(f"Trying OpenRouter for {len(jobs)} jobs")
            response_text = await self._call_openrouter(prompt)
            results = self._parse_llm_response(response_text)
            if results and len(results) == len(jobs):
                logger.info(f"OpenRouter returned valid results for {len(jobs)} jobs")
                return [self._validate_score_result(r) for r in results]
            logger.warning(
                f"OpenRouter returned {len(results)} results, expected {len(jobs)}"
            )
        except Exception as e:
            logger.error(f"OpenRouter scoring failed: {e}")

        # Deterministic fallback
        logger.info("Using deterministic scoring fallback")
        return self._deterministic_fallback(
            jobs,
            candidate_skills,
            candidate_years,
            candidate_locations,
            remote_preference,
            weight_skills,
            weight_experience,
            weight_location,
        )

    def _deterministic_fallback(
        self,
        jobs: list[dict[str, Any]],
        candidate_skills: list[str],
        candidate_years: float,
        candidate_locations: list[str],
        remote_preference: str,
        weight_skills: float,
        weight_experience: float,
        weight_location: float,
    ) -> list[dict[str, Any]]:
        """Fall back to deterministic scoring for a batch of jobs."""
        results = []
        for job in jobs:
            content = job.get("content", "")
            scores = compute_scores(
                job_skills=extract_skills(content),
                job_seniority=extract_seniority(content),
                job_years_exp=extract_years_experience(content),
                job_location=extract_location_info(content),
                candidate_skills=candidate_skills,
                candidate_years=candidate_years,
                candidate_locations=candidate_locations,
                candidate_remote_pref=remote_preference,
                weight_skills=weight_skills,
                weight_experience=weight_experience,
                weight_location=weight_location,
            )
            results.append(scores)
        return results

    async def score_single(
        self,
        job_content: str,
        job_title: str,
        candidate_skills: list[str],
        candidate_years: float,
        candidate_locations: list[str],
        remote_preference: str,
        weight_skills: float = 0.5,
        weight_experience: float = 0.3,
        weight_location: float = 0.2,
    ) -> dict[str, Any]:
        """Score a single job (convenience wrapper around score_batch)."""
        jobs = [{"title": job_title, "content": job_content}]
        results = await self.score_batch(
            jobs,
            candidate_skills,
            candidate_years,
            candidate_locations,
            remote_preference,
            weight_skills,
            weight_experience,
            weight_location,
        )
        return results[0] if results else {}

    async def close(self):
        """Clean up HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Singleton instance
_scorer: LLMScorer | None = None


def get_llm_scorer() -> LLMScorer:
    """Get the singleton LLM scorer instance."""
    global _scorer
    if _scorer is None:
        _scorer = LLMScorer()
    return _scorer
