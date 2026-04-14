"""
backend/services/rag_service.py — Orchestrates retrieve → generate for regulatory queries.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.query import retrieve
from src.generate import generate

# Defaults driven by eval results — override via .env
_DEFAULT_SOURCE_SYSTEM = os.getenv("RAG_SOURCE_SYSTEM", "federal_regulations")
_DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "6"))
_DEFAULT_STRATEGY = os.getenv("LLM_CALL_STRATEGY", "sequential")


async def run_query(
    query: str,
    top_k: int | None = None,
    title_number: int | None = None,
    source_id: str | None = None,
    corpus_type: str | None = None,
    strategy: str | None = None,
    source_system: str | None = None,
) -> dict:
    """
    Full RAG pipeline: retrieve → generate → return structured result.
    Runs synchronous operations in a thread pool.
    """
    resolved_top_k = top_k if top_k is not None else _DEFAULT_TOP_K
    resolved_strategy = strategy or _DEFAULT_STRATEGY
    resolved_source_system = source_system or _DEFAULT_SOURCE_SYSTEM

    loop = asyncio.get_event_loop()

    # Retrieve (synchronous pgvector query)
    chunks, timing = await loop.run_in_executor(
        None,
        lambda: retrieve(
            query,
            top_k=resolved_top_k,
            source_system=resolved_source_system,
            title_number=title_number,
            source_id=source_id,
            corpus_type=corpus_type,
        ),
    )

    # Generate (synchronous Anthropic call)
    gen_result = await loop.run_in_executor(
        None,
        lambda: generate(query, chunks, strategy=resolved_strategy),
    )

    qr = gen_result.response
    return {
        "plain_english": qr.plain_english,
        "legal_language": qr.legal_language,
        "citations": [c.model_dump() for c in qr.citations],
        "not_found": qr.not_found,
        "strategy_used": qr.strategy_used,
        "latency_ms": int(gen_result.latency_ms),
        "input_tokens": gen_result.input_tokens,
        "output_tokens": gen_result.output_tokens,
        "timing": timing,
    }
