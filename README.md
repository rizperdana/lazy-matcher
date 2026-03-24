# lazy-matcher

Async job matching pipeline. Submits 1–10 job descriptions, scores them against a stored candidate profile in PostgreSQL, and shows results via a polling React frontend.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Next.js UI  │────▶│  FastAPI API  │────▶│  PostgreSQL  │
│  (port 3456) │     │  (port 8000) │     │  (port 5432) │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │  Worker(s)   │
                    │ FOR UPDATE   │
                    │ SKIP LOCKED  │
                    └──────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL

### Backend

```bash
cd backend

# Create venv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install psycopg2-binary

# Set database URL (adjust for your Postgres)
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/lazy_matcher"

# Run migrations
alembic upgrade head

# Seed candidate data
python -m app.db.seed

# Run tests
pytest tests/test_matches.py -v

# Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start worker (in another terminal)
python -m app.worker.runner
```

### Frontend

```bash
cd frontend

# Install deps
npm install

# Run Playwright tests
npx playwright test

# Start dev server
npx next dev -p 3456
```

### Docker Compose

```bash
docker compose up --build
```

This starts: PostgreSQL, API server, two workers, and the frontend.

## Scoring Engine

Deterministic hybrid scoring (keyword extraction + rules):

| Weight | Component    | How it scores                                          |
|--------|-------------|--------------------------------------------------------|
| 50%    | Skills      | Overlap between candidate skills and job description   |
| 30%    | Experience  | Seniority match + years of experience alignment        |
| 20%    | Location    | Remote preference + location keywords                  |

Recommendations: `strong_match` (≥80), `good_match` (≥60), `partial_match` (≥40), `weak_match` (<40).

## API

### POST /api/v1/matches

Submit a batch of job descriptions.

```json
{
  "items": [
    {"content": "Senior Python Engineer — FastAPI, PostgreSQL, Docker"},
    {"content": "Frontend Developer — React, TypeScript, 3+ years"}
  ]
}
```

### GET /api/v1/matches/{job_id}

Get match result for a specific job.

### GET /api/v1/matches?status=&limit=&offset=

List all match jobs with optional filters.

## Database Schema

- `candidates` — Candidate profiles (name, email, title, location)
- `candidate_profiles` — Experience details, seniority, preferences
- `candidate_skills` — Skills with level and years used
- `match_batches` — Groups of submitted job descriptions
- `match_jobs` — Individual job scoring results with status, scores, and recommendations

## Testing

```bash
# Backend integration tests
cd backend && source .venv/bin/activate
export DATABASE_URL="postgresql+asyncpg://anon@127.0.0.1:5432/lazy_matcher"
pytest tests/test_matches.py -v

# Frontend Playwright tests
cd frontend
npx playwright test
```
