"""
src/sources — Phase 10 Part C: pluggable registry of forward-looking live
sources.

The eCFR corpus is the codified regulation (what the rule says today); live
sources cover what the rule is BECOMING — proposed rules, NPRMs, and final
rules not yet codified. Each source registers a description (drives routing),
a fetch client, a citation format, a status vocabulary, and a cache TTL.
Later sources (GAO reports, agency guidance, state registers) slot in here
without router changes.

Live-source results are never corpus content: they are cached with a short
TTL and always stamped with fetched_at.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass(frozen=True)
class LiveSource:
    name: str
    description: str                 # natural-language, drives routing prompts
    citation_format: str             # e.g. "91 FR 47162"
    status_vocabulary: tuple[str, ...]
    cache_ttl_s: int
    fetch: Callable                  # (query, titles) -> list[dict]


def _build_registry() -> dict[str, LiveSource]:
    from src.sources.federal_register import fetch_documents
    from src.sources.regulations_gov import enrich_documents

    return {
        "federal_register": LiveSource(
            name="federal_register",
            description=(
                "The Federal Register daily journal: proposed rules (NPRMs) and "
                "final rules before codification — what regulations are becoming."
            ),
            citation_format="XX FR YYYYY",
            status_vocabulary=(
                "proposed", "comment-open", "pending", "final-not-yet-codified"),
            cache_ttl_s=1800,
            fetch=fetch_documents,
        ),
        "regulations_gov": LiveSource(
            name="regulations_gov",
            description=(
                "regulations.gov docket layer: comment-period status and docket "
                "documents for proposed rules (enrichment, not primary search)."
            ),
            citation_format="Docket ID",
            status_vocabulary=("comment-open", "comment-closed"),
            cache_ttl_s=1800,
            fetch=enrich_documents,
        ),
    }


REGISTRY: dict[str, LiveSource] = _build_registry()


def fetch_forward_documents(query: str, titles: list[int] | None = None,
                            cfr_parts: list[tuple[int, str]] | None = None,
                            limit: int = 8) -> dict:
    """
    One-stop fetch for the forward-looking path: Federal Register full-text
    search first; if it misses and the caller knows the affected CFR parts
    (from the codified retrieval's top chunks), fall back to part-scoped
    lookups. Documents are enriched with regulations.gov docket links.
    Returns {"documents": [...], "fetched_at": iso, "sources": [...]} —
    fetched_at is mandatory provenance for anything served from a live source.
    """
    from src.sources.federal_register import fetch_by_cfr_part

    docs: list[dict] = []
    seen: set[str] = set()
    # Precision first: documents affecting the CFR parts the codified
    # retrieval identified as relevant.
    for title, part in (cfr_parts or [])[:3]:
        for d in fetch_by_cfr_part(title, part, limit=4):
            if d["document_number"] not in seen:
                seen.add(d["document_number"])
                docs.append(d)
    # Breadth second: relevance-ranked full-text search fills remaining slots.
    if len(docs) < limit:
        fr = REGISTRY["federal_register"]
        for d in fr.fetch(query, titles=titles, limit=limit):
            if d["document_number"] not in seen:
                seen.add(d["document_number"])
                docs.append(d)
    docs = docs[:limit]
    docs = REGISTRY["regulations_gov"].fetch(docs)
    return {
        "documents": docs,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": [s for s in REGISTRY if docs or s == "federal_register"],
    }
