"""
src/query.py — Retrieval engine using pgvector cosine similarity search.

IMPORTANT: ALL queries include AND status = 'active' to enforce corpus freshness.
This filter is applied here in a single place — never per call-site.

Usage (standalone):
    python src/query.py "What are the labeling requirements for organic produce?"
    python src/query.py "OSHA fall protection requirements" --title 29
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

openai_client = OpenAI()


@dataclass
class RetrievedChunk:
    """A retrieved chunk with similarity score and CFR citation metadata."""
    chunk_id: str
    source_system: str
    source_id: str
    corpus_type: str
    location_reference: str
    # CFR-specific
    title_number: int | None
    part_number: str | None
    section_number: str | None
    section_heading: str | None
    agency: str | None
    cfr_reference: str | None
    effective_date: str | None
    # Content
    chunk_text: str
    similarity: float

    def citation_string(self) -> str:
        """Formatted CFR citation for display."""
        if self.cfr_reference:
            if self.section_heading:
                return f"{self.cfr_reference} \u2014 {self.section_heading}"
            return self.cfr_reference
        return self.location_reference or self.source_id

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "cfr_reference": self.cfr_reference,
            "section_heading": self.section_heading,
            "citation": self.citation_string(),
            "similarity": round(self.similarity, 4),
            "chunk_text": self.chunk_text,
        }


def _embed(text: str) -> list[float]:
    """Embed a single query string."""
    response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding


def retrieve(
    query: str,
    top_k: int = 6,
    source_system: str = "federal_regulations",
    title_number: int | None = None,
    source_id: str | None = None,
    corpus_type: str | None = None,
) -> tuple[list[RetrievedChunk], dict]:
    """
    Retrieve the top_k most relevant chunks for a query.

    ALWAYS filters to status = 'active' — this is the corpus freshness guarantee.

    Args:
        query:         Natural language question
        top_k:         Number of chunks to return
        source_system: Filter by corpus (default: "federal_regulations")
        title_number:  Optional filter by CFR title number (e.g., 7)
        source_id:     Optional filter by source slug (e.g., "cfr_title_7")
        corpus_type:   Optional filter by type (e.g., "cfr")

    Returns:
        (chunks, timing) — chunks sorted by descending similarity, timing dict in ms
    """
    timing: dict[str, float] = {}

    t0 = time.time()
    query_vector = _embed(query)
    timing["embed_ms"] = round((time.time() - t0) * 1000, 1)

    # Build filter conditions
    # status = 'active' is ALWAYS included — enforced here, not per call-site
    conditions = ["source_system = %s", "status = 'active'"]
    params: list = [source_system]

    if title_number is not None:
        conditions.append("title_number = %s")
        params.append(title_number)
    if source_id:
        conditions.append("source_id = %s")
        params.append(source_id)
    if corpus_type:
        conditions.append("corpus_type = %s")
        params.append(corpus_type)

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            id::text,
            source_system,
            source_id,
            corpus_type,
            location_reference,
            title_number,
            part_number,
            section_number,
            section_heading,
            agency,
            cfr_reference,
            effective_date::text,
            chunk_text,
            1 - (embedding <=> %s::vector) AS similarity
        FROM chunks
        WHERE {where_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """

    t0 = time.time()
    conn = psycopg.connect(DATABASE_URL)
    try:
        rows = conn.execute(
            sql,
            [query_vector] + params + [query_vector, top_k]
        ).fetchall()
    finally:
        conn.close()
    timing["retrieve_ms"] = round((time.time() - t0) * 1000, 1)

    chunks = [
        RetrievedChunk(
            chunk_id=row[0],
            source_system=row[1],
            source_id=row[2],
            corpus_type=row[3],
            location_reference=row[4],
            title_number=row[5],
            part_number=row[6],
            section_number=row[7],
            section_heading=row[8],
            agency=row[9],
            cfr_reference=row[10],
            effective_date=row[11],
            chunk_text=row[12],
            similarity=float(row[13]),
        )
        for row in rows
    ]

    return chunks, timing


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a context block for the LLM prompt."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Source {i}: {chunk.citation_string()}]\n{chunk.chunk_text}")
    return "\n\n---\n\n".join(parts)


def list_titles(source_system: str = "federal_regulations") -> list[dict]:
    """Return all indexed CFR titles with chunk counts."""
    conn = psycopg.connect(DATABASE_URL)
    try:
        rows = conn.execute(
            """
            SELECT title_number, source_id, agency, COUNT(*) as chunk_count,
                   MAX(effective_date)::text as latest_date
            FROM chunks
            WHERE source_system = %s AND status = 'active'
            GROUP BY title_number, source_id, agency
            ORDER BY title_number
            """,
            (source_system,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "title_number": row[0],
            "source_id": row[1],
            "agency": row[2],
            "chunk_count": row[3],
            "latest_date": row[4],
        }
        for row in rows
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the Federal Regulation RAG")
    parser.add_argument("query", help="Question to ask")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--title", type=int, help="Filter to a specific CFR title number")
    args = parser.parse_args()

    chunks, timing = retrieve(args.query, top_k=args.top_k, title_number=args.title)
    print(f"\nQuery: {args.query}")
    print(f"Timing: embed={timing['embed_ms']}ms  retrieve={timing['retrieve_ms']}ms\n")
    for i, chunk in enumerate(chunks, 1):
        print(f"[{i}] {chunk.citation_string()} (sim={chunk.similarity:.3f})")
        print(f"    {chunk.chunk_text[:200]}...\n")
