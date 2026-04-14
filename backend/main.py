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

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes import query, sources
from backend.services import db_service

app = FastAPI(
    title="Federal Regulation RAG API",
    description="RAG-powered federal regulatory query engine with plain English and legal language outputs",
    version="1.0.0",
)

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
    """Health check — validates DB connectivity."""
    try:
        pool = await db_service.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        return {"status": "error", "db": str(exc)}
