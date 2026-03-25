"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.matches import router as matches_router
from app.services.cache import cache_stats

settings = get_settings()

app = FastAPI(
    title="Lazy Matcher API",
    description="Async job matching pipeline",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches_router, prefix=settings.API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "cache": cache_stats()}
