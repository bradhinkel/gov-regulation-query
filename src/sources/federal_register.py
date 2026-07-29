"""
src/sources/federal_register.py — Federal Register documents client (Part C).

Free, unauthenticated API (https://www.federalregister.gov/developers/
documentation/api/v1). Searches proposed rules (PRORULE) and final rules
(RULE) matching a query, restricted to the corpus's CFR titles, and derives a
hard status per document:

    comment-open             PRORULE, comment period still open
    pending                  PRORULE, comment period closed (awaiting final)
    proposed                 PRORULE, no comment dates published
    final-not-yet-codified   RULE with a future effective date

Results are cached in-process with a short TTL (proposed-rule state changes
daily; comment windows get extended) and must always be served with the
registry's fetched_at stamp — never treated as static corpus content.
"""

import os
import time
from datetime import date

import httpx

FR_API_BASE = os.getenv("FR_API_BASE", "https://www.federalregister.gov/api/v1")
CORPUS_TITLES = [7, 10, 14, 21, 29, 40, 42, 49]
_TIMEOUT = 15.0
_TTL_S = int(os.getenv("FR_CACHE_TTL", "1800"))

_FIELDS = [
    "title", "type", "abstract", "document_number", "citation",
    "publication_date", "comments_close_on", "comment_url",
    "regulation_id_numbers", "docket_ids", "agencies", "cfr_references",
    "html_url", "effective_on",
]

_cache: dict[tuple, tuple[float, list[dict]]] = {}


def _status(doc_type: str, comments_close_on: str | None,
            effective_on: str | None) -> str | None:
    today = date.today().isoformat()
    if doc_type == "Proposed Rule":
        if comments_close_on and comments_close_on >= today:
            return "comment-open"
        if comments_close_on:
            return "pending"
        return "proposed"
    if doc_type == "Rule":
        if effective_on and effective_on > today:
            return "final-not-yet-codified"
        return None  # already effective — that's the codified corpus's job
    return None


def _parse(doc: dict) -> dict | None:
    status = _status(doc.get("type", ""), doc.get("comments_close_on"),
                     doc.get("effective_on"))
    if status is None:
        return None
    agencies = [a.get("name") for a in doc.get("agencies") or [] if a.get("name")]
    cfr_refs = [
        f"{r['title']} CFR part {r['part']}"
        for r in doc.get("cfr_references") or []
        if r.get("title") and r.get("part")
    ]
    return {
        "source": "federal_register",
        "status": status,
        "doc_type": doc.get("type"),
        "title": doc.get("title"),
        "abstract": (doc.get("abstract") or "")[:1200],
        "document_number": doc.get("document_number"),
        "fr_citation": doc.get("citation"),          # "91 FR 47162"
        "publication_date": doc.get("publication_date"),
        "comments_close_on": doc.get("comments_close_on"),
        "effective_on": doc.get("effective_on"),
        "rins": doc.get("regulation_id_numbers") or [],
        "docket_ids": doc.get("docket_ids") or [],
        "agencies": agencies,
        "cfr_references": cfr_refs,
        "url": doc.get("html_url"),
    }


def fetch_by_cfr_part(title: int, part: str, limit: int = 5) -> list[dict]:
    """
    Documents affecting a specific CFR title/part — the precision fallback
    when full-text term search misses. Aligns FR results with the codified
    citation space (the retrieved chunks tell us which parts matter).
    """
    key = ("part", title, part, limit)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]
    params: list[tuple[str, str]] = [
        ("per_page", str(limit * 2)),
        ("order", "newest"),
        ("conditions[cfr][title]", str(title)),
        ("conditions[cfr][part]", str(part)),
    ]
    params += [("conditions[type][]", t) for t in ("PRORULE", "RULE")]
    params += [("fields[]", f) for f in _FIELDS]
    docs: list[dict] = []
    try:
        r = httpx.get(f"{FR_API_BASE}/documents.json", params=params,
                      timeout=_TIMEOUT)
        r.raise_for_status()
        for raw in r.json().get("results", []):
            parsed = _parse(raw)
            if parsed:
                docs.append(parsed)
            if len(docs) >= limit:
                break
    except (httpx.HTTPError, ValueError, KeyError):
        return []
    _cache[key] = (time.time(), docs)
    return docs


def fetch_documents(query: str, titles: list[int] | None = None,
                    limit: int = 8) -> list[dict]:
    """
    Search recent proposed + future-effective final rules matching `query`.
    `titles` restricts to specific CFR titles (default: the 8 corpus titles).
    Returns parsed document dicts, newest first. Failures return [] — the
    caller falls back to a codified answer rather than erroring.
    """
    titles = titles or CORPUS_TITLES
    key = (query.strip().lower(), tuple(sorted(titles)), limit)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]

    # relevance ordering (newest-first surfaces unrelated recent docs) inside
    # a two-year recency window (older proposals are usually dead or final).
    since = date.today().replace(year=date.today().year - 2).isoformat()
    params: list[tuple[str, str]] = [
        ("per_page", str(limit * 2)),
        ("order", "relevance"),
        ("conditions[term]", query),
        ("conditions[publication_date][gte]", since),
    ]
    params += [("conditions[type][]", t) for t in ("PRORULE", "RULE")]
    params += [("fields[]", f) for f in _FIELDS]

    docs: list[dict] = []
    try:
        # One request per title set is wasteful; the API accepts repeated
        # conditions[cfr][title] but ANDs them — so query without the CFR
        # condition and filter client-side against the corpus titles.
        r = httpx.get(f"{FR_API_BASE}/documents.json", params=params,
                      timeout=_TIMEOUT)
        r.raise_for_status()
        for raw in r.json().get("results", []):
            parsed = _parse(raw)
            if parsed is None:
                continue
            doc_titles = {int(ref.split()[0]) for ref in parsed["cfr_references"]
                          if ref.split()[0].isdigit()}
            if doc_titles and not doc_titles & set(titles):
                continue
            docs.append(parsed)
            if len(docs) >= limit:
                break
    except (httpx.HTTPError, ValueError, KeyError):
        return []

    _cache[key] = (time.time(), docs)
    return docs
