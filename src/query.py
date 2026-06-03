"""
src/query.py — Retrieval engine using pgvector cosine similarity search.

IMPORTANT: ALL queries include AND status = 'active' to enforce corpus freshness.
This filter is applied here in a single place — never per call-site.

search_mode:
  "vector"       — pure cosine similarity (default)
  "hybrid"       — Reciprocal Rank Fusion of vector + PostgreSQL full-text search (FTS).
                   FTS column: text_search (tsvector over chunk_text + cfr_reference +
                   section_heading + section_number). Hybrid mode improves recall on
                   queries that contain exact CFR references or regulatory keywords.
  "hierarchical" — retrieve top_k paragraph chunks via vector search, deduplicate to
                   unique sections, fetch ALL sibling paragraphs from DB per section,
                   and assemble one coherent section chunk per section. Combines the
                   retrieval precision of paragraph-level embeddings with the generation
                   quality of full-section context.

Usage (standalone):
    python src/query.py "What are the labeling requirements for organic produce?"
    python src/query.py "OSHA fall protection requirements" --title 29
    python src/query.py "7 CFR 205.300 organic labeling" --hybrid
    python src/query.py "organic labeling requirements" --hierarchical
"""

import argparse
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import anthropic
import psycopg
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
REWRITE_MODEL = "claude-haiku-4-5-20251001"

_anthropic_client = anthropic.Anthropic()

if "voyage" in EMBEDDING_MODEL:
    import voyageai
    _voyage_client = voyageai.Client()
    _openai_client = None
else:
    from openai import OpenAI
    _voyage_client = None
    _openai_client = OpenAI()

_REWRITE_SYSTEM = """\
You are a federal regulatory search assistant. Rewrite the user's question to maximize \
retrieval from a CFR (Code of Federal Regulations) vector database.

Expand the question to include:
- Regulatory terminology as it appears in the CFR
- Relevant CFR title/part numbers if implied by the question
- Synonyms and related regulatory concepts
- The specific regulatory language likely to appear in the answer

Return ONLY the rewritten query. No explanation. Keep it under 80 words."""

_HYDE_SYSTEM = """\
You are a federal regulatory expert. Given a question about federal regulations, generate \
a hypothetical CFR (Code of Federal Regulations) passage that would directly answer it.

Write in formal regulatory language exactly as it appears in the CFR:
- Use precise regulatory terminology and imperative voice ("shall", "must", "may not")
- Include specific thresholds, dates, timeframes, or conditions if implied by the question
- Reference CFR section numbers where natural (e.g. "Pursuant to § 205.301...")
- Match the dense, structured register of actual CFR text

Return ONLY the hypothetical regulatory passage. No introduction, no explanation. \
Under 200 words."""


def _rewrite_query(query: str) -> str:
    """Use a fast LLM call to expand the user query into regulatory language."""
    response = _anthropic_client.messages.create(
        model=REWRITE_MODEL,
        max_tokens=150,
        messages=[{"role": "user", "content": query}],
        system=_REWRITE_SYSTEM,
    )
    return response.content[0].text.strip() if response.content else query


def _hyde_query(query: str) -> str:
    """Generate a hypothetical CFR document that would answer the query (HyDE).

    The hypothetical document is written in CFR register language, so its embedding
    is closer to actual CFR sections than a plain-English question embedding. This
    bridges the language gap between how users ask questions and how regulations are
    written — typically the largest single source of retrieval miss rate.
    """
    response = _anthropic_client.messages.create(
        model=REWRITE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": f"Question: {query}"}],
        system=_HYDE_SYSTEM,
    )
    return response.content[0].text.strip() if response.content else query

# Columns selected in every retrieval query — shared by vector and FTS paths.
_COLS = """
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
    chunk_text
"""


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
    """Embed a single query string using the configured embedding model."""
    if _voyage_client:
        result = _voyage_client.embed([text], model=EMBEDDING_MODEL, input_type="query")
        return result.embeddings[0]
    response = _openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding


def _build_where(
    source_system: str,
    title_number: int | None,
    source_id: str | None,
    corpus_type: str | None,
) -> tuple[str, list]:
    """Build WHERE clause and params. status = 'active' always included."""
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
    return " AND ".join(conditions), params


def _row_to_chunk(row: tuple, score: float) -> RetrievedChunk:
    return RetrievedChunk(
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
        similarity=score,
    )


def _strip_context_prefix(chunk_text: str) -> str:
    """Remove the [cfr_ref]\\nheading\\n\\n prefix from a paragraph chunk's text.

    The parser always writes: context_prefix + paragraph_body, where context_prefix
    ends with '\\n\\n' when a section heading is present, or '\\n' otherwise.
    Returns the bare paragraph body, or the original text if no prefix is found.
    """
    if "\n\n" in chunk_text:
        return chunk_text.split("\n\n", 1)[1]
    if "\n" in chunk_text:
        return chunk_text.split("\n", 1)[1]
    return chunk_text


def _fetch_section_siblings(
    conn: psycopg.Connection,
    source_system: str,
    source_id: str,
    section_number: str,
) -> list[tuple]:
    """Fetch all paragraph chunks belonging to the same § section, ordered by chunk_index."""
    sql = f"""
        SELECT {_COLS}, chunk_index
        FROM chunks
        WHERE source_system = %s
          AND source_id = %s
          AND section_number = %s
          AND status = 'active'
        ORDER BY chunk_index ASC
    """
    return conn.execute(sql, (source_system, source_id, section_number)).fetchall()


def _assemble_hierarchical_chunks(
    retrieved_chunks: list[RetrievedChunk],
    conn: psycopg.Connection,
    source_system: str,
    max_sections: int = 6,
    max_chars_per_section: int = 4000,
) -> list[RetrievedChunk]:
    """
    Given paragraph-level retrieved chunks, deduplicate to unique sections and
    reassemble each section from all its sibling paragraphs.

    For each unique (source_id, section_number) in the retrieved set:
      - Fetches ALL sibling paragraphs from the DB (not just the retrieved ones)
      - Assembles them in reading order with one section header
      - Carries the max similarity score from the retrieved paragraphs of that section
      - Truncates to max_chars_per_section to prevent large sections from
        dominating the context window

    Args:
        max_sections:          Cap on number of assembled sections returned.
                               Keeps total context comparable to a top_k=6 section run.
        max_chars_per_section: Hard character limit per assembled section.
                               Prevents very long CFR sections (e.g. substance tables)
                               from flooding the LLM context window.

    Chunks without a section_number are passed through unchanged.
    Sections are returned ordered by their best paragraph similarity (descending).
    """
    hierarchical: list[RetrievedChunk] = []
    passthrough: list[RetrievedChunk] = []

    # Deduplicate to unique sections, tracking best similarity and representative chunk
    best_score: dict[tuple, float] = {}
    representative: dict[tuple, RetrievedChunk] = {}

    for chunk in retrieved_chunks:
        if not chunk.section_number:
            passthrough.append(chunk)
            continue
        key = (chunk.source_id, chunk.section_number)
        if key not in best_score or chunk.similarity > best_score[key]:
            best_score[key] = chunk.similarity
            representative[key] = chunk

    # Sort sections by best paragraph similarity descending, then cap at max_sections
    sorted_keys = sorted(best_score, key=best_score.__getitem__, reverse=True)[:max_sections]

    for key in sorted_keys:
        rep = representative[key]
        source_id, section_number = key
        sibling_rows = _fetch_section_siblings(conn, source_system, source_id, section_number)

        if not sibling_rows:
            # Fallback: return the retrieved paragraph as-is
            hierarchical.append(rep)
            continue

        # Build section header once, then append stripped paragraph bodies
        header = f"[{rep.cfr_reference}]\n" if rep.cfr_reference else ""
        if rep.section_heading:
            header += f"{rep.section_heading}\n\n"

        bodies = [_strip_context_prefix(row[12]) for row in sibling_rows]
        full_text = header + "\n\n".join(b for b in bodies if b)

        # Truncate at a sentence boundary near the limit to avoid mid-sentence cuts
        if len(full_text) > max_chars_per_section:
            cut = full_text.rfind(". ", 0, max_chars_per_section)
            if cut == -1:
                cut = max_chars_per_section
            full_text = full_text[:cut + 1]

        hierarchical.append(RetrievedChunk(
            chunk_id=rep.chunk_id,
            source_system=rep.source_system,
            source_id=rep.source_id,
            corpus_type=rep.corpus_type,
            location_reference=rep.location_reference,
            title_number=rep.title_number,
            part_number=rep.part_number,
            section_number=rep.section_number,
            section_heading=rep.section_heading,
            agency=rep.agency,
            cfr_reference=rep.cfr_reference,
            effective_date=rep.effective_date,
            chunk_text=full_text,
            similarity=best_score[key],
        ))

    return hierarchical + passthrough


def _vector_search(
    conn: psycopg.Connection,
    query_vector: list[float],
    where_clause: str,
    base_params: list,
    top_k: int,
) -> list[tuple]:
    sql = f"""
        SELECT {_COLS}
        FROM chunks
        WHERE {where_clause}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    return conn.execute(sql, base_params + [query_vector, top_k]).fetchall()


def _fts_search(
    conn: psycopg.Connection,
    query_text: str,
    where_clause: str,
    base_params: list,
    top_k: int,
) -> list[tuple]:
    sql = f"""
        SELECT {_COLS}
        FROM chunks
        WHERE {where_clause}
          AND text_search @@ plainto_tsquery('english', %s)
        ORDER BY ts_rank_cd(text_search, plainto_tsquery('english', %s)) DESC
        LIMIT %s
    """
    return conn.execute(sql, base_params + [query_text, query_text, top_k]).fetchall()


def _rrf_merge(
    vector_rows: list[tuple],
    fts_rows: list[tuple],
    top_k: int,
    k: int = 60,
) -> list[tuple[tuple, float]]:
    """
    Reciprocal Rank Fusion of two ranked result lists.
    RRF score = Σ 1 / (rank + k) across all lists.
    k=60 is the standard constant that down-weights very low-ranked results.
    """
    rrf_scores: dict[str, float] = defaultdict(float)
    row_by_id: dict[str, tuple] = {}

    for rank, row in enumerate(vector_rows, 1):
        chunk_id = row[0]
        rrf_scores[chunk_id] += 1.0 / (rank + k)
        row_by_id[chunk_id] = row

    for rank, row in enumerate(fts_rows, 1):
        chunk_id = row[0]
        rrf_scores[chunk_id] += 1.0 / (rank + k)
        if chunk_id not in row_by_id:
            row_by_id[chunk_id] = row

    sorted_ids = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)[:top_k]
    return [(row_by_id[cid], rrf_scores[cid]) for cid in sorted_ids]


def retrieve(
    query: str,
    top_k: int = 6,
    source_system: str = "federal_regulations",
    title_number: int | None = None,
    source_id: str | None = None,
    corpus_type: str | None = None,
    search_mode: str = "vector",
    query_rewrite: bool = False,
    use_hyde: bool = False,
    max_sections: int = 6,
    max_chars_per_section: int = 4000,
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
        search_mode:   "vector" (cosine similarity only), "hybrid" (vector + FTS via RRF),
                       or "hierarchical" (paragraph retrieval + parent section assembly)

    Returns:
        (chunks, timing) — chunks sorted by descending similarity, timing dict in ms
    """
    timing: dict[str, float] = {}

    retrieval_query = query
    if use_hyde:
        # HyDE: generate a hypothetical CFR passage, embed that instead of the raw query.
        # use_hyde takes precedence over query_rewrite when both are set.
        t0 = time.time()
        retrieval_query = _hyde_query(query)
        timing["hyde_ms"] = round((time.time() - t0) * 1000, 1)
    elif query_rewrite:
        t0 = time.time()
        retrieval_query = _rewrite_query(query)
        timing["rewrite_ms"] = round((time.time() - t0) * 1000, 1)

    t0 = time.time()
    query_vector = _embed(retrieval_query)
    timing["embed_ms"] = round((time.time() - t0) * 1000, 1)

    where_clause, base_params = _build_where(source_system, title_number, source_id, corpus_type)

    t0 = time.time()
    conn = psycopg.connect(DATABASE_URL)
    try:
        if search_mode == "hybrid":
            vector_rows = _vector_search(conn, query_vector, where_clause, base_params, top_k)
            fts_rows = _fts_search(conn, retrieval_query, where_clause, base_params, top_k)
            merged = _rrf_merge(vector_rows, fts_rows, top_k)
            chunks = [_row_to_chunk(row, score) for row, score in merged]
        elif search_mode == "hierarchical":
            rows = _vector_search(conn, query_vector, where_clause, base_params, top_k)
            scores_sql = f"""
                SELECT 1 - (embedding <=> %s::vector) AS similarity
                FROM chunks
                WHERE {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            score_rows = conn.execute(scores_sql, [query_vector] + base_params + [query_vector, top_k]).fetchall()
            scores = [float(r[0]) for r in score_rows]
            para_chunks = [_row_to_chunk(row, score) for row, score in zip(rows, scores)]
            chunks = _assemble_hierarchical_chunks(
                para_chunks, conn, source_system,
                max_sections=max_sections,
                max_chars_per_section=max_chars_per_section,
            )
        else:
            rows = _vector_search(conn, query_vector, where_clause, base_params, top_k)
            # Compute cosine similarity scores for vector-only path
            scores_sql = f"""
                SELECT 1 - (embedding <=> %s::vector) AS similarity
                FROM chunks
                WHERE {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            score_rows = conn.execute(scores_sql, [query_vector] + base_params + [query_vector, top_k]).fetchall()
            scores = [float(r[0]) for r in score_rows]
            chunks = [_row_to_chunk(row, score) for row, score in zip(rows, scores)]
    finally:
        conn.close()
    timing["retrieve_ms"] = round((time.time() - t0) * 1000, 1)

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
            SELECT title_number, source_id, MIN(agency) as agency,
                   COUNT(*) as chunk_count,
                   MAX(effective_date)::text as latest_date
            FROM chunks
            WHERE source_system = %s AND status = 'active'
            GROUP BY title_number, source_id
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


def fetch_section_versions(
    cfr_references: list[str],
    source_system: str = "federal_regulations",
) -> dict:
    """
    Phase 9.4 — fetch current + prior versions of the given sections for temporal
    "what changed?" queries.

    Returns { cfr_reference: {"active": [RetrievedChunk...],
                              "archived": [RetrievedChunk...]} }
    ordered newest-first by effective_date. Archived chunks are the superseded
    text retained by the versioned-replacement swap.
    """
    if not cfr_references:
        return {}
    conn = psycopg.connect(DATABASE_URL)
    try:
        rows = conn.execute(
            f"""
            SELECT {_COLS}, status
            FROM chunks
            WHERE source_system = %s
              AND cfr_reference = ANY(%s)
              AND status IN ('active', 'archived')
            ORDER BY cfr_reference, effective_date DESC, chunk_index ASC
            """,
            (source_system, cfr_references),
        ).fetchall()
    finally:
        conn.close()

    result: dict = {}
    for row in rows:
        status = row[13]
        chunk = _row_to_chunk(row[:13], 0.0)
        bucket = result.setdefault(chunk.cfr_reference, {"active": [], "archived": []})
        if status in bucket:
            bucket[status].append(chunk)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the Federal Regulation RAG")
    parser.add_argument("query", help="Question to ask")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--title", type=int, help="Filter to a specific CFR title number")
    parser.add_argument("--hybrid", action="store_true", help="Use hybrid vector + FTS retrieval")
    parser.add_argument("--hierarchical", action="store_true", help="Use hierarchical retrieval (paragraph search + section assembly)")
    parser.add_argument("--hyde", action="store_true", help="Use HyDE: embed a hypothetical CFR answer instead of the raw query")
    args = parser.parse_args()

    if args.hierarchical:
        mode = "hierarchical"
    elif args.hybrid:
        mode = "hybrid"
    else:
        mode = "vector"
    chunks, timing = retrieve(args.query, top_k=args.top_k, title_number=args.title, search_mode=mode, use_hyde=args.hyde)
    print(f"\nQuery: {args.query}")
    print(f"Mode:   {mode}")
    print(f"Timing: embed={timing['embed_ms']}ms  retrieve={timing['retrieve_ms']}ms\n")
    for i, chunk in enumerate(chunks, 1):
        print(f"[{i}] {chunk.citation_string()} (score={chunk.similarity:.4f})")
        print(f"    {chunk.chunk_text[:200]}...\n")
