"""
backend/routes/query.py — POST /query and GET /history endpoints.

POST /query returns Server-Sent Events:
  event: status   — {"status": "retrieving"} | {"status": "generating"}
  event: result   — full QueryResponse JSON
  event: error    — {"error": "message"}
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from typing import AsyncIterator

from backend.models.schemas import (
    QueryRequest, QueryResponse, QueryHistoryResponse, CitationOut
)
from backend.services import rag_service, db_service

router = APIRouter()


async def _sse_stream(request: QueryRequest) -> AsyncIterator[str]:
    """Generate SSE events for a regulatory query."""

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    try:
        yield sse("status", {"status": "retrieving", "query": request.query})

        result = await rag_service.run_query(
            query=request.query,
            top_k=request.top_k,
            title_number=request.title_number,
            source_id=request.source_id,
            corpus_type=request.corpus_type,
            strategy=request.strategy,
            source_system=request.source_system,
        )

        yield sse("status", {"status": "generating"})

        # Persist to DB
        saved = await db_service.save_query(
            query_text=request.query,
            plain_english=result["plain_english"],
            legal_language=result["legal_language"],
            citations=result["citations"],
            llm_strategy=result["strategy_used"],
            latency_ms=result["latency_ms"],
        )

        # Build citation_string for each citation
        citations_out = []
        for c in result["citations"]:
            cs = c.get("cfr_reference", "")
            if c.get("section_heading"):
                cs += f" \u2014 {c['section_heading']}"
            citations_out.append({**c, "citation_string": cs})

        response_payload = {
            "id": saved["id"],
            "query": request.query,
            "plain_english": result["plain_english"],
            "legal_language": result["legal_language"],
            "citations": citations_out,
            "not_found": result["not_found"],
            "strategy_used": result["strategy_used"],
            "latency_ms": result["latency_ms"],
            "created_at": saved["created_at"],
        }

        yield sse("result", response_payload)

    except Exception as exc:
        yield sse("error", {"error": str(exc)})


@router.post("/query")
async def query_endpoint(request: QueryRequest):
    """
    Submit a regulatory query. Returns Server-Sent Events stream.
    Events: status → result (or error)
    """
    return StreamingResponse(
        _sse_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history", response_model=QueryHistoryResponse)
async def history(page: int = 1, page_size: int = 20):
    """Return paginated query history."""
    items, total = await db_service.get_queries(page=page, page_size=page_size)

    responses = [
        QueryResponse(
            id=item["id"],
            query=item["query_text"],
            plain_english=item["plain_english"],
            legal_language=item["legal_language"],
            citations=[
                CitationOut(
                    cfr_reference=c.get("cfr_reference", ""),
                    title_number=c.get("title_number"),
                    part_number=c.get("part_number"),
                    section_number=c.get("section_number"),
                    section_heading=c.get("section_heading"),
                    agency=c.get("agency"),
                    source_id=c.get("source_id", ""),
                    citation_string=c.get("citation_string"),
                )
                for c in item["citations"]
            ],
            not_found=not bool(item["plain_english"]),
            strategy_used=item["llm_strategy"] or "single",
            latency_ms=item["latency_ms"] or 0,
            created_at=item["created_at"],
        )
        for item in items
    ]

    return QueryHistoryResponse(
        items=responses,
        total=total,
        page=page,
        page_size=page_size,
    )
