"""
backend/main.py — FastAPI entry point for the Federal Regulation RAG API.
Runs on localhost:8002
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes import query, sources
from backend.services import db_service
from backend.rate_limit import limiter

app = FastAPI(
    title="Federal Regulation RAG API",
    description="RAG-powered federal regulatory query engine with plain English and legal language outputs",
    version="1.0.0",
)

# Phase 8.5: per-IP rate limiting. The limiter is attached per-route in
# routes/query.py; here we register state + the 429 handler (sets Retry-After).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3002",
        os.getenv("BASE_URL", "http://localhost:8002"),
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db_service.init_db()


app.include_router(query.router, tags=["query"])
app.include_router(sources.router, tags=["sources"])


@app.get("/health")
async def health():
    """Health check — DB connectivity + corpus freshness (Phase 9.6)."""
    try:
        pool = await db_service.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        corpus = await db_service.get_sync_health()
        eval_health = await db_service.get_eval_health()
        return {"status": "ok", "db": "connected", "corpus": corpus, "eval": eval_health}
    except Exception as exc:
        return {"status": "error", "db": str(exc)}
