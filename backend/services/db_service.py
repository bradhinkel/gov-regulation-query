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
) -> dict:
    pool = await get_pool()
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO queries
                (id, query_text, source_system, plain_english, legal_language,
                 citations, llm_strategy, latency_ms, created_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
            """,
            item_id, query_text, source_system, plain_english, legal_language,
            json.dumps(citations), llm_strategy, latency_ms, now,
        )

    return {
        "id": item_id,
        "query_text": query_text,
        "plain_english": plain_english,
        "legal_language": legal_language,
        "citations": citations,
        "llm_strategy": llm_strategy,
        "latency_ms": latency_ms,
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
                   llm_strategy, latency_ms, created_at
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
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
    return items, total
