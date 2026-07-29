"""
src/sources/regulations_gov.py — regulations.gov v4 docket enrichment (Part C).

Adds the docket/comment layer to Federal Register documents: a link-through
per docket always, plus docket title verification when a DATA_GOV_API_KEY is
configured (https://api.data.gov — free key; v4 rate limit is 1000 req/hour,
we spend at most one request per distinct docket per TTL window).

Enrichment is best-effort: no key or an API failure leaves the documents
untouched except for the link-through URLs.
"""

import os
import time

import httpx

REGS_API_BASE = os.getenv("REGS_API_BASE", "https://api.regulations.gov/v4")
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")
_TIMEOUT = 10.0
_TTL_S = int(os.getenv("REGS_CACHE_TTL", "1800"))

_docket_cache: dict[str, tuple[float, dict | None]] = {}


def _docket_info(docket_id: str) -> dict | None:
    """Docket metadata via /v4/dockets/{id}; cached; None without key/on error."""
    if not DATA_GOV_API_KEY:
        return None
    hit = _docket_cache.get(docket_id)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]
    info = None
    try:
        r = httpx.get(f"{REGS_API_BASE}/dockets/{docket_id}",
                      params={"api_key": DATA_GOV_API_KEY}, timeout=_TIMEOUT)
        if r.status_code == 200:
            attrs = r.json().get("data", {}).get("attributes", {})
            info = {"docket_title": attrs.get("title"),
                    "rin": attrs.get("rin")}
    except (httpx.HTTPError, ValueError):
        info = None
    _docket_cache[docket_id] = (time.time(), info)
    return info


def enrich_documents(docs: list[dict]) -> list[dict]:
    """Attach docket link-throughs (always) and docket metadata (with a key)."""
    for doc in docs:
        links = []
        for docket_id in doc.get("docket_ids", [])[:3]:
            entry = {"docket_id": docket_id,
                     "url": f"https://www.regulations.gov/docket/{docket_id}"}
            info = _docket_info(docket_id)
            if info:
                entry.update(info)
            links.append(entry)
        doc["dockets"] = links
    return docs
