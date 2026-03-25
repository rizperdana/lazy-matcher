# lazy-matcher

Async job matching pipeline. Submits 1–10 job descriptions, scores them against a stored candidate profile in PostgreSQL, and shows results via a polling React frontend.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Next.js UI  │────▶│  FastAPI API  │────▶│  PostgreSQL  │
│  (Vercel)    │     │  (Render)    │     │  (Neon)      │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                     ┌──────▼───────┐
                     │  Worker(s)   │
                     │ FOR UPDATE   │
                     │ SKIP LOCKED  │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │  LLM Scoring │
                     │  Gemini API  │
                     │  (OpenRouter │
                     │   fallback)  │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │ Upstash Redis│
                     │ (queue/cache)│
                     └──────────────┘
```

## Quick Start

### Option 1: Docker Compose (Recommended)

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
# Create .env with your credentials
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://your-neon-connection-string
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
- **Worker 1** — processes jobs from Redis queue
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

# Set DATABASE_URL (Neon connection string)
export DATABASE_URL="postgresql+asyncpg://user:pass@ep-xxx-pooler.neon.tech/db?ssl=require"
export DATABASE_URL_SYNC="postgresql://user:pass@ep-xxx-pooler.neon.tech/db?sslmode=require"

# Run migrations
alembic upgrade head

# Seed candidate data
python -m app.db.seed

# Run tests
PYTHON_GIL=0 pytest tests/test_matches.py -v

# Start API server
PYTHON_GIL=0 uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start worker (in another terminal)
PYTHON_GIL=0 python -m app.worker.runner
```

#### Frontend

```bash
cd frontend

# Install deps
npm install

# Run Playwright tests (needs backend running)
npx playwright test

# Start dev server
npm run dev
```

## Scoring Engine

### LLM-Based Scoring (Primary)

Uses Gemini 2.5 Flash Lite as primary LLM with OpenRouter fallback:

| Component    | Description                                    |
|-------------|------------------------------------------------|
| Skills      | LLM analyzes job requirements vs candidate     |
| Experience  | LLM evaluates seniority and years alignment    |
| Location    | LLM considers remote/hybrid/onsite preferences |
| Batch       | Multiple jobs scored in one API call           |

### Deterministic Fallback

Keyword extraction + rule-based scoring (used when LLM unavailable):

| Weight | Component    | How it scores                                          |
|--------|-------------|--------------------------------------------------------|
| 50%    | Skills      | Overlap between candidate skills and job description   |
| 30%    | Experience  | Seniority match + years of experience alignment        |
| 20%    | Location    | Remote preference + location keywords                  |

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_LLM_SCORING` | `true` | Enable LLM scoring (falls back to deterministic on failure) |
| `LLM_BATCH_SIZE` | `5` | Max jobs per LLM API call |
| `GEMINI_AI_KEY` | - | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Gemini model name |
| `OPENROUTER_KEY` | - | OpenRouter API key (fallback) |
| `OPENROUTER_MODEL` | `stepfun/step-3.5-flash:free` | OpenRouter model name |

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

### GET /health

Health check with cache status.

## Deployment

### Backend (Render)

The `render.yaml` blueprint deploys:
- API service (uvicorn)
- Worker service (polls PostgreSQL + Redis queue for jobs)

**Required environment variables:**
- `DATABASE_URL` — Neon PostgreSQL connection string (asyncpg)
- `DATABASE_URL_SYNC` — Neon PostgreSQL connection string (psycopg2, for Alembic)
- `GEMINI_AI_KEY` — Google Gemini API key
- `OPENROUTER_KEY` — OpenRouter fallback key
- `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` — Upstash Redis for job queue

### Frontend (Vercel)

```bash
cd frontend
npm run build
vercel --prod
```

Uses relative API URLs (`/api/v1/*`) with Next.js rewrites to backend.

## Database Schema

- `candidates` — Candidate profiles (name, email, title, location)
- `candidate_profiles` — Experience details, seniority, preferences
- `candidate_skills` — Skills with level and years used
- `match_batches` — Groups of submitted job descriptions
- `match_jobs` — Individual job scoring results with status, scores, and recommendations

## Testing

```bash
# Backend integration tests (against Neon)
cd backend
PYTHON_GIL=0 pytest tests/test_matches.py -v

# Frontend Playwright tests (needs backend running)
cd frontend
npx playwright test
```
