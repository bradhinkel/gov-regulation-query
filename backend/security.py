"""
backend/security.py — Phase 8.5 input/output validation for the query path.

Three layers run around the RAG pipeline:
  1. validate_query()  — pre-embedding input validation (length, control chars)
  2. intent gate       — see src.generate.classify_intent (off-topic rejection)
  3. check_output()    — post-generation content validation (URL allowlist, code/script)

The retrieval-grounding constraint (status='active' + low-similarity → not_found)
is the implicit first line of defense; these checks are the explicit layers on top.
"""

import re

# ── Input validation ─────────────────────────────────────────────────────────

MAX_QUERY_LENGTH = 750  # DoS / embedding-quality cap, not an injection defense.

# C0 control chars except tab (\x09), newline (\x0a), carriage return (\x0d).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class QueryValidationError(Exception):
    """Raised when an inbound query fails pre-embedding validation (HTTP 400)."""


def validate_query(query: str) -> str:
    """
    Validate and normalize an inbound query before any embedding or LLM call.

    Returns the stripped query. Raises QueryValidationError (→ HTTP 400) on:
      - empty / whitespace-only input
      - length over MAX_QUERY_LENGTH characters
      - null bytes or Unicode C0 control characters
    """
    if query is None:
        raise QueryValidationError("Query is required.")

    cleaned = query.strip()
    if not cleaned:
        raise QueryValidationError("Query cannot be empty.")

    if len(cleaned) > MAX_QUERY_LENGTH:
        raise QueryValidationError(
            f"Query exceeds maximum length. Please limit your question to "
            f"{MAX_QUERY_LENGTH} characters."
        )

    if _CONTROL_CHARS.search(cleaned):
        raise QueryValidationError("Query contains invalid control characters.")

    return cleaned


# ── Output validation ────────────────────────────────────────────────────────

# Generated regulatory answers should only ever cite official sources.
# federalregister.gov + regulations.gov added in Phase 10 Part C — without
# them every forward-looking answer would be auto-downgraded by this check.
ALLOWED_URL_DOMAINS = ("ecfr.gov", "cfr.gov", "govinfo.gov",
                       "federalregister.gov", "regulations.gov")

_URL_RE = re.compile(r"https?://([^/\s)\"']+)", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```")
_SCRIPT_RE = re.compile(r"<\s*script", re.IGNORECASE)


def _host_allowed(host: str) -> bool:
    host = host.lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in ALLOWED_URL_DOMAINS)


def check_output(text: str) -> dict:
    """
    Sanity-check generated text before returning it to the user.

    Returns a dict:
      {"reject": bool, "downgrade": bool, "reason": str | None}

    - reject=True   → return an error instead of the generated content
                      (code fences or <script> tags appeared in a regulatory answer)
    - downgrade=True → serve the content but force confidence to low
                       (a URL outside the official-source allowlist appeared)
    """
    if not text:
        return {"reject": False, "downgrade": False, "reason": None}

    if _CODE_BLOCK_RE.search(text) or _SCRIPT_RE.search(text):
        return {
            "reject": True,
            "downgrade": False,
            "reason": "generated text contained a code block or script tag",
        }

    bad_urls = [host for host in _URL_RE.findall(text) if not _host_allowed(host)]
    if bad_urls:
        return {
            "reject": False,
            "downgrade": True,
            "reason": f"non-allowlisted URL(s) in generated text: {sorted(set(bad_urls))}",
        }

    return {"reject": False, "downgrade": False, "reason": None}
