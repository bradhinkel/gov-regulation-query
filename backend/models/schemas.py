"""Request / response Pydantic models for the Federal Regulation RAG API."""

from typing import Optional
from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    title_number: Optional[int] = None    # Filter to a specific CFR title (e.g. 7)
    source_id: Optional[str] = None       # Filter by source slug (e.g. "cfr_title_7")
    corpus_type: Optional[str] = None     # Filter by type (e.g. "cfr")
    source_system: Optional[str] = None   # Override corpus (default: federal_regulations)
    top_k: Optional[int] = None           # None → use RAG_TOP_K from env (default 6)
    strategy: Optional[str] = None        # Override LLM_CALL_STRATEGY ("single" | "sequential")


class CitationOut(BaseModel):
    cfr_reference: str
    title_number: Optional[int] = None
    part_number: Optional[str] = None
    section_number: Optional[str] = None
    section_heading: Optional[str] = None
    agency: Optional[str] = None
    source_id: str
    citation_string: Optional[str] = None


class QueryResponse(BaseModel):
    id: str
    query: str
    plain_english: str
    legal_language: str
    citations: list[CitationOut]
    not_found: bool
    strategy_used: str
    latency_ms: int
    created_at: str


class QueryHistoryResponse(BaseModel):
    items: list[QueryResponse]
    total: int
    page: int
    page_size: int


class SourceTitle(BaseModel):
    title_number: Optional[int] = None
    source_id: str
    agency: Optional[str] = None
    chunk_count: int
    latest_date: Optional[str] = None


class SourcesResponse(BaseModel):
    sources: list[SourceTitle]
    total_chunks: int
