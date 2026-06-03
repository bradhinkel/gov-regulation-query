"""
backend/services/db_service.py — PostgreSQL persistence for query history.

Table: queries
  id              UUID PRIMARY KEY
  query_text      TEXT
  source_system   TEXT
  plain_english   TEXT
  legal_language  TEXT
  citations       JSONB
  llm_strategy    TEXT
  latency_ms      INTEGER
  not_found       BOOLEAN
  confidence      JSONB
  created_at      TIMESTAMPTZ
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag",
)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def init_db():
    """Verify DB connectivity. Table + indexes are created by src/db/schema.sql."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1 FROM queries LIMIT 1")


async def save_query(
    query_text: str,
    plain_english: str,
    legal_language: str,
    citations: list[dict],
    llm_strategy: str,
    latency_ms: int,
    source_system: str = "federal_regulations",
    not_found: bool = False,
    confidence: Optional[dict] = None,
) -> dict:
    pool = await get_pool()
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO queries
                (id, query_text, source_system, plain_english, legal_language,
                 citations, llm_strategy, latency_ms, not_found, confidence, created_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10::jsonb, $11)
            """,
            item_id, query_text, source_system, plain_english, legal_language,
            json.dumps(citations), llm_strategy, latency_ms,
            not_found, json.dumps(confidence) if confidence else None, now,
        )

    return {
        "id": item_id,
        "query_text": query_text,
        "plain_english": plain_english,
        "legal_language": legal_language,
        "citations": citations,
        "llm_strategy": llm_strategy,
        "latency_ms": latency_ms,
        "not_found": not_found,
        "confidence": confidence,
        "created_at": now.isoformat(),
    }


async def get_queries(
    page: int = 1,
    page_size: int = 20,
    source_system: str = "federal_regulations",
) -> tuple[list[dict], int]:
    pool = await get_pool()
    offset = (page - 1) * page_size

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, query_text, plain_english, legal_language, citations,
                   llm_strategy, latency_ms, not_found, confidence, created_at
            FROM queries
            WHERE source_system = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            source_system, page_size, offset,
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM queries WHERE source_system = $1", source_system
        )

    items = [
        {
            "id": str(r["id"]),
            "query_text": r["query_text"],
            "plain_english": r["plain_english"] or "",
            "legal_language": r["legal_language"] or "",
            "citations": (
                json.loads(r["citations"])
                if isinstance(r["citations"], str)
                else (list(r["citations"]) if r["citations"] else [])
            ),
            "llm_strategy": r["llm_strategy"],
            "latency_ms": r["latency_ms"],
            "not_found": r["not_found"] or False,
            "confidence": (
                json.loads(r["confidence"])
                if isinstance(r["confidence"], str)
                else (dict(r["confidence"]) if r["confidence"] else None)
            ),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
    return items, total


async def get_sync_health() -> dict:
    """
    Corpus freshness for /health (Phase 9.6): active size, per-title watermarks,
    and the last incremental-sync run. Resilient if the sync tables don't exist
    yet (returns what it can).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        active = await conn.fetchval("SELECT count(*) FROM chunks WHERE status = 'active'")
        try:
            titles = await conn.fetch(
                "SELECT title_number, last_synced_date, "
                "(CURRENT_DATE - last_synced_date) AS days_old "
                "FROM sync_state ORDER BY title_number"
            )
            last = await conn.fetchrow(
                "SELECT run_at, status, titles_changed, sections_updated, sections_removed "
                "FROM sync_runs ORDER BY id DESC LIMIT 1"
            )
        except asyncpg.exceptions.UndefinedTableError:
            return {"active_chunks": active, "sync": None}

    return {
        "active_chunks": active,
        "titles_tracked": len(titles),
        "oldest_title_days": max((t["days_old"] for t in titles), default=None),
        "title_as_of": {
            str(t["title_number"]): t["last_synced_date"].isoformat() for t in titles
        },
        "last_sync": (
            {
                "run_at": last["run_at"].isoformat(),
                "status": last["status"],
                "titles_changed": last["titles_changed"],
                "sections_updated": last["sections_updated"],
                "sections_removed": last["sections_removed"],
            }
            if last
            else None
        ),
    }
