"""
backend/routes/query.py — POST /query and GET /history endpoints.

POST /query returns Server-Sent Events:
  event: status     — {"status": "classifying"|"retrieving"|"generating"}
  event: off_topic  — {"tier": "off_topic", "message": "..."}   (Phase 8.5 gate)
  event: result     — full QueryResponse JSON
  event: error      — {"error": "message"}

Status events fire at the correct point in the pipeline:
  "classifying" → before anything (intent gate)
  "retrieving"  → before vector search
  "generating"  → after retrieval, before LLM call

Phase 8.5 security layers wrap this path: input validation + rate limiting on
the endpoint, the intent gate below, and output validation before the result.
"""

import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncIterator

from backend.models.schemas import (
    QueryRequest, QueryResponse, QueryHistoryResponse, CitationOut, ConfidenceOut
)
from backend.services import rag_service, db_service
from backend.rate_limit import limiter, QUERY_RATE_LIMITS
from backend.security import validate_query, check_output, QueryValidationError

router = APIRouter()

_OFF_TOPIC_MESSAGE = (
    "This system answers questions about U.S. federal regulations. "
    "Please rephrase your question as a regulatory inquiry."
)


async def _sse_stream(request: QueryRequest) -> AsyncIterator[str]:
    """Generate SSE events for a regulatory query."""

    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    try:
        # Step 0: Intent gate (Phase 8.5) — reject off-topic before spending
        # tokens on retrieval or generation.
        yield sse("status", {"status": "classifying"})
        is_regulatory = await rag_service.run_classify(request.query)
        if not is_regulatory:
            yield sse("off_topic", {"tier": "off_topic", "message": _OFF_TOPIC_MESSAGE})
            return

        # Step 1: Retrieve
        yield sse("status", {"status": "retrieving", "query": request.query})

        chunks, timing = await rag_service.run_retrieve(
            query=request.query,
            top_k=request.top_k,
            title_number=request.title_number,
            source_id=request.source_id,
            corpus_type=request.corpus_type,
            source_system=request.source_system,
            use_hyde=request.use_hyde,
        )

        # Step 2: Generate
        yield sse("status", {"status": "generating"})

        result = await rag_service.run_generate(
            query=request.query,
            chunks=chunks,
            timing=timing,
            strategy=request.strategy,
        )

        # Step 2.5: Output content validation (Phase 8.5). Reject answers that
        # smuggle code/script; downgrade confidence for non-official URLs.
        if not result["not_found"]:
            verdict = check_output(
                f"{result['plain_english']}\n{result['legal_language']}"
            )
            if verdict["reject"]:
                yield sse("error", {
                    "error": "The generated response failed a content safety check "
                             "and was withheld. Please rephrase your question.",
                })
                return
            if verdict["downgrade"] and result.get("confidence"):
                result["confidence"]["tier"] = "low"

        # Persist to DB
        saved = await db_service.save_query(
            query_text=request.query,
            plain_english=result["plain_english"],
            legal_language=result["legal_language"],
            citations=result["citations"],
            llm_strategy=result["strategy_used"],
            latency_ms=result["latency_ms"],
            not_found=result["not_found"],
            confidence=result["confidence"],
        )

        # Build citation_string for each citation
        citations_out = []
        for c in result["citations"]:
            cs = c.get("cfr_reference", "")
            if c.get("section_heading"):
                cs += f" \u2014 {c['section_heading']}"
            citations_out.append({**c, "citation_string": cs})

        conf = result.get("confidence")
        response_payload = {
            "id": saved["id"],
            "query": request.query,
            "plain_english": result["plain_english"],
            "legal_language": result["legal_language"],
            "citations": citations_out,
            "not_found": result["not_found"],
            "strategy_used": result["strategy_used"],
            "latency_ms": result["latency_ms"],
            "confidence": conf,
            "created_at": saved["created_at"],
        }

        yield sse("result", response_payload)

    except Exception as exc:
        yield sse("error", {"error": str(exc)})


@router.post("/query")
@limiter.limit(QUERY_RATE_LIMITS)
async def query_endpoint(request: Request, payload: QueryRequest):
    """
    Submit a regulatory query. Returns Server-Sent Events stream.
    Events: status(classifying→retrieving→generating) → result | off_topic | error

    Phase 8.5: input is validated (HTTP 400) and rate limited (HTTP 429) before
    the stream opens. `request: Request` is required by the slowapi limiter.
    """
    try:
        payload.query = validate_query(payload.query)
    except QueryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return StreamingResponse(
        _sse_stream(payload),
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
            not_found=item.get("not_found", not bool(item["plain_english"])),
            strategy_used=item["llm_strategy"] or "sequential",
            latency_ms=item["latency_ms"] or 0,
            confidence=ConfidenceOut(**item["confidence"]) if item.get("confidence") else None,
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
