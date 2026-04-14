"""
backend/routes/sources.py — GET /sources endpoint.
Returns all indexed CFR titles with chunk counts.
"""

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.models.schemas import SourceTitle, SourcesResponse
from src.query import list_titles

router = APIRouter()


@router.get("/sources", response_model=SourcesResponse)
async def sources():
    """List all indexed CFR titles with their chunk counts."""
    loop = asyncio.get_event_loop()
    titles = await loop.run_in_executor(None, list_titles)

    return SourcesResponse(
        sources=[SourceTitle(**t) for t in titles],
        total_chunks=sum(t["chunk_count"] for t in titles),
    )
