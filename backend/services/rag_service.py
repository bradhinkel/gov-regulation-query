"""
backend/services/rag_service.py — Orchestrates retrieve → generate for regulatory queries.

Exposes two async steps so the SSE stream can emit status events between them:
  run_retrieve()  — vector search, returns (chunks, timing)
  run_generate()  — LLM generation, returns structured result dict
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.query import retrieve, fetch_section_versions
from src.generate import generate, classify_intent, is_temporal_query, generate_temporal

# Defaults driven by eval results (Phase 4 winner: top_k=10, sequential Haiku)
_DEFAULT_SOURCE_SYSTEM = os.getenv("RAG_SOURCE_SYSTEM", "federal_regulations")
_DEFAULT_TOP_K = int(os.getenv("RAG_TOP_K", "10"))
_DEFAULT_STRATEGY = os.getenv("LLM_CALL_STRATEGY", "sequential")


async def run_classify(query: str) -> bool:
    """
    Phase 8.5 intent gate. Returns True if the query is regulatory, False if
    off-topic. Runs the synchronous Haiku classifier in a thread pool.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: classify_intent(query))


async def run_retrieve(
    query: str,
    top_k: int | None = None,
    title_number: int | None = None,
    source_id: str | None = None,
    corpus_type: str | None = None,
    source_system: str | None = None,
    use_hyde: bool = False,
) -> tuple[list, dict]:
    """
    Run the retrieval step only. Returns (chunks, timing).
    Runs synchronous pgvector query in a thread pool.
    """
    resolved_top_k = top_k if top_k is not None else _DEFAULT_TOP_K
    resolved_source_system = source_system or _DEFAULT_SOURCE_SYSTEM

    loop = asyncio.get_event_loop()
    chunks, timing = await loop.run_in_executor(
        None,
        lambda: retrieve(
            query,
            top_k=resolved_top_k,
            source_system=resolved_source_system,
            title_number=title_number,
            source_id=source_id,
            corpus_type=corpus_type,
            use_hyde=use_hyde,
        ),
    )
    return chunks, timing


async def run_generate(
    query: str,
    chunks: list,
    timing: dict,
    strategy: str | None = None,
) -> dict:
    """
    Run the generation step only. Returns structured result dict.
    Runs synchronous Anthropic call in a thread pool.
    """
    resolved_strategy = strategy or _DEFAULT_STRATEGY

    loop = asyncio.get_event_loop()
    gen_result = await loop.run_in_executor(
        None,
        lambda: generate(query, chunks, strategy=resolved_strategy),
    )
    return _to_result_dict(gen_result, timing)


def _to_result_dict(gen_result, timing: dict, temporal: bool = False) -> dict:
    """Shape a GenerationResult into the SSE result payload."""
    qr = gen_result.response
    conf = gen_result.confidence
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
        "temporal": temporal,
        "confidence": {
            "score": conf.score,
            "tier": conf.tier,
            "retrieval_score": conf.retrieval_score,
            "citation_coverage": conf.citation_coverage,
            "verified_citations": conf.verified_citations,
            "unverified_citations": conf.unverified_citations,
        } if conf else None,
    }


def is_temporal(query: str) -> bool:
    """Phase 9.4 intent check (sync, cheap)."""
    return is_temporal_query(query)


async def run_temporal(query: str, chunks: list, timing: dict, max_refs: int = 8) -> dict | None:
    """
    Build a 'what changed?' answer from current vs archived versions of the top
    retrieved sections. Returns a result dict, or None if no section has recorded
    changes (the caller then falls back to a normal answer).
    """
    refs: list[str] = []
    for c in chunks:
        ref = getattr(c, "cfr_reference", None)
        if ref and ref not in refs:
            refs.append(ref)
        if len(refs) >= max_refs:
            break

    loop = asyncio.get_event_loop()
    versions = await loop.run_in_executor(None, lambda: fetch_section_versions(refs))
    gen_result = await loop.run_in_executor(
        None, lambda: generate_temporal(query, versions, chunks)
    )
    if gen_result is None:
        return None
    return _to_result_dict(gen_result, timing, temporal=True)
