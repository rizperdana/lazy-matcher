# lazy-matcher

Async job matching pipeline. Submits 1–10 job descriptions (text or URL), scores them against a stored candidate profile in PostgreSQL, and shows results via a polling React frontend.

Supports **URL extraction** — paste a job board link (Glints, Indeed, etc.) and the system auto-extracts structured job data via JSON-LD.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Next.js UI    │────▶│   FastAPI API    │────▶│   PostgreSQL     │
│  (port 3000)    │     │  (port 8000)     │     │  (Neon)          │
└─────────────────┘     └──────┬───────────┘     └──────────────────┘
                               │
                         ┌──────▼───────────┐
                         │   Worker(s)      │
                         │  SELECT FOR UPDATE
                         │  SKIP LOCKED     │
                         └──────┬───────────┘
                                │
                  ┌─────────────┼─────────────┐
                  │             │             │
           ┌──────▼─────┐ ┌────▼────┐ ┌──────▼──────┐
           │Redis Queue │ │  Gemini │ │ Deterministic│
           │(Upstash)   │ │ Primary │ │  Fallback   │
           └────────────┘ │ + OpenR │ └─────────────┘
                          │ fallback│
                          └─────────┘
```

## Quick Start

### Option 1: Docker Compose (Recommended)

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
# Create .env with your credentials
cat > .env << 'EOF'
DATABASE_URL=postgresql://neondb_owner:password@ep-xxx-pooler.neon.tech/neondb?ssl=require
UPSTASH_REDIS_REST_URL=https://your-instance.upstash.io
UPSTASH_REDIS_REST_TOKEN=your-upstash-token
GEMINI_AI_KEY=your-gemini-key
OPENROUTER_KEY=your-openrouter-key
EOF

# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

Services started:
- **API** — http://localhost:8000 (FastAPI + Alembic migrations + seed)
- **Worker 1** — processes jobs from Redis queue + DB polling
- **Worker 2** — second worker for parallelism
- **Frontend** — http://localhost:3000 (Next.js with API proxy)

### Option 2: Local Development

#### Prerequisites

- Python 3.11+ (3.14 requires `PYTHON_GIL=0`)
- Node.js 18+
- Neon PostgreSQL account
- Upstash Redis account

#### Backend

```bash
cd backend

# Create venv and install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install psycopg2-binary

# Set DATABASE_URL — use plain postgresql:// (auto-converted to asyncpg)
export DATABASE_URL="postgresql://user:pass@ep-xxx-pooler.neon.tech/db?ssl=require"

# DATABASE_URL_SYNC is auto-derived from DATABASE_URL if not set
# Override if needed (for Alembic migrations):
export DATABASE_URL_SYNC="postgresql://user:pass@ep-xxx-pooler.neon.tech/db?ssl=require"

# Run migrations
alembic upgrade head

# Seed candidate data
python -m app.db.seed

# Run tests
PYTHON_GIL=0 pytest tests/test_matches.py -v

# Start API server
PYTHON_GIL=0 uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start worker (in another terminal)
# --poll-interval: seconds between DB polls (default 2)
PYTHON_GIL=0 python -m app.worker.runner --worker-id worker-1 --poll-interval 2
```

#### Frontend

```bash
cd frontend

# Install deps
npm install

# Run Playwright tests (needs backend running)
npx playwright test --reporter=line

# Start dev server
npm run dev
```

## How It Works

### Job Submission

1. **POST** 1–10 job descriptions (text or URLs) to `/api/v1/matches`
2. Jobs are stored in PostgreSQL with `status=pending`
3. Job IDs are pushed to Redis queue for immediate processing
4. Workers claim jobs using `SELECT FOR UPDATE SKIP LOCKED` (safe concurrent processing)

### URL Extraction

When a URL is submitted, the worker:

1. Fetches the page with a browser User-Agent header
2. Attempts **JSON-LD extraction** — many job boards (Glints, Indeed, LinkedIn) embed `JobPosting` schema.org structured data in `<script type="application/ld+json">` tags
3. Extracts: title, description, skills, experience, salary, location, company, employment type, benefits
4. Falls back to **BeautifulSoup** text extraction for non-JSON-LD sites

### Scoring

Scoring has two modes with automatic fallback:

| Mode | Description | When Used |
|------|-------------|-----------|
| **LLM (Gemini)** | Batch scoring via Gemini 2.5 Flash Lite | Default when `GEMINI_AI_KEY` is set |
| **LLM (OpenRouter)** | Fallback via OpenRouter API | When Gemini fails |
| **Deterministic** | Keyword extraction + rule-based scoring | When LLM unavailable or `USE_LLM_SCORING=false` |

#### Scoring Dimensions

| Weight | Component    | How It Scores                                          |
|--------|-------------|--------------------------------------------------------|
| 50%    | Skills      | Overlap between candidate skills and job requirements  |
| 30%    | Experience  | Seniority match + years of experience alignment        |
| 20%    | Location    | Remote preference + location compatibility             |

#### Caching

Scores are cached in Upstash Redis (keyed by `source_hash + candidate_id`) with a 1-hour TTL. Duplicate submissions get instant cache hits.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Neon connection | PostgreSQL connection string (auto-converted to asyncpg) |
| `DATABASE_URL_SYNC` | Auto-derived | Sync PG connection for Alembic migrations |
| `UPSTASH_REDIS_REST_URL` | - | Upstash Redis URL |
| `UPSTASH_REDIS_REST_TOKEN` | - | Upstash Redis token |
| `GEMINI_AI_KEY` | - | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Gemini model name |
| `OPENROUTER_KEY` | - | OpenRouter API key (fallback) |
| `OPENROUTER_MODEL` | `stepfun/step-3.5-flash:free` | OpenRouter model name |
| `USE_LLM_SCORING` | `true` | Enable LLM scoring (falls back to deterministic) |
| `LLM_BATCH_SIZE` | `5` | Max jobs per LLM API call |
| `WEIGHT_SKILLS` | `0.5` | Skills scoring weight |
| `WEIGHT_EXPERIENCE` | `0.3` | Experience scoring weight |
| `WEIGHT_LOCATION` | `0.2` | Location scoring weight |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |
| `WORKER_POLL_INTERVAL` | `2.0` | Worker DB poll interval (seconds) |
| `API_PREFIX` | `/api/v1` | API route prefix |

## API

### POST /api/v1/matches

Submit a batch of 1–10 job descriptions or URLs.

```json
{
  "items": [
    {"content": "Senior Python Engineer — FastAPI, PostgreSQL, Docker"},
    {"content": "https://glints.com/id/opportunities/jobs/12345"},
    {"content": "Frontend Developer — React, TypeScript, 3+ years", "source_type": "text"}
  ]
}
```

**Response** (201):
```json
{
  "batch_id": "uuid",
  "job_count": 3,
  "jobs": [
    {"id": "uuid", "status": "pending", ...}
  ]
}
```

### GET /api/v1/matches/{job_id}

Get match result for a specific job.

### GET /api/v1/matches?status=&limit=&offset=

List all match jobs with optional filters.

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter: `pending`, `processing`, `completed`, `failed` |
| `limit` | int | Results per page (1–100, default 20) |
| `offset` | int | Pagination offset (default 0) |

### GET /health

Health check with cache status.

## Database Schema

- `candidates` — Candidate profiles (name, email, title, location)
- `candidate_profiles` — Experience details, seniority, preferences, remote preference
- `candidate_skills` — Skills with level and years used
- `match_batches` — Groups of submitted job descriptions
- `match_jobs` — Individual job scoring results with status, scores, recommendations, retry tracking, and worker locking

## Deployment

### Docker Compose

The `docker-compose.yml` runs all services locally:
- `api` — FastAPI (port 8000)
- `worker-1`, `worker-2` — Background workers
- `frontend` — Next.js (port 3000)

### Render

The `render.yaml` blueprint deploys:
- API service (uvicorn, free tier, Oregon)
- Worker service (polls PostgreSQL + Redis queue)

### Leapcell

The `leapcell.yaml` deploys the API service.

### Frontend (Vercel)

```bash
cd frontend
npm run build
vercel --prod
```

Uses relative API URLs (`/api/v1/*`) with Next.js rewrites to the backend URL set via `NEXT_PUBLIC_API_URL`.

## Testing

```bash
# Backend integration tests (3/3 pass, runs against Neon)
cd backend
PYTHON_GIL=0 pytest tests/test_matches.py -v

# Frontend Playwright tests (6/6 pass, needs backend running on port 8000)
cd frontend
npx playwright test --reporter=line
```

## Project Structure

```
backend/
  app/
    api/          # FastAPI route handlers
    core/         # Config, settings
    db/           # Session, seed script
    models/       # SQLAlchemy ORM models
    schemas/      # Pydantic request/response schemas
    services/     # scoring, llm_scoring, cache, notifier
    worker/       # Background worker (runner.py)
  alembic/        # Database migrations
  tests/          # Integration tests
frontend/
  src/
    app/          # Next.js app directory
    components/   # MatchDashboard, MatchForm, JobCard, ResultsList, StatusSummary
    lib/          # API client, providers (TanStack Query)
  tests/          # Playwright E2E tests
```
