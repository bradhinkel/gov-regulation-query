"""
src/escalation.py — Phase 10 Part B: selective inline judge escalation.

The deterministic confidence composite (src/generate.py compute_confidence)
runs on every query, unchanged. Only queries in the *ambiguous band* pay for
an inline judge call (src/judge.py, inline mode — no ground-truth reference):

  (a) composite within ESCALATION_MARGIN of a tier boundary (0.75 / 0.50), or
  (b) high retrieval_score with low citation_coverage — the case where the
      regex proxy is least trustworthy (grounded paraphrase scores 0 coverage).

On disagreement the judge wins: unsupported claims are downgraded, grounded
paraphrase the regex under-scored is upgraded. The Phase 8.5 output-check
downgrade still runs *after* escalation and wins — a security downgrade is
never overridden upward by the judge (backend/routes/query.py ordering).

A judge failure fails open: the deterministic tier stands and the error is
recorded in the quality payload. Band thresholds are env-overridable; validate
them against real traffic with scripts/replay_escalation.py before changing.
"""

import os

from src.judge import judge_grounding

# Band definition. Margin validated against real droplet traffic on
# 2026-07-28 (41 persisted queries, scripts/replay_escalation.py):
#   0.06 -> 14.6% escalation, 0.08 -> 22.0%, 0.10 -> 39.0%.
# 0.06 keeps comfortable headroom under the <25% target on a small sample.
ESCALATION_MARGIN = float(os.getenv("ESCALATION_MARGIN", "0.06"))
# Rule (b): retrieval found strongly similar text but the answer cites little
# of it — exactly where citation_coverage under-scores grounded paraphrase.
ESCALATION_RETRIEVAL_HIGH = float(os.getenv("ESCALATION_RETRIEVAL_HIGH", "0.50"))
ESCALATION_COVERAGE_LOW = float(os.getenv("ESCALATION_COVERAGE_LOW", "0.50"))

# Tier thresholds — must mirror src/generate.py.
TIER_HIGH_THRESHOLD = float(os.getenv("CONF_TIER_HIGH", "0.75"))
TIER_MED_THRESHOLD = float(os.getenv("CONF_TIER_MEDIUM", "0.50"))


def escalation_reason(confidence: dict | None) -> str | None:
    """
    Why this answer is in the ambiguous band, or None if it isn't.
    Pure function of the confidence payload — reused verbatim by the replay
    script so measured rates match production behavior.
    """
    if not confidence or confidence.get("tier") == "not_found":
        return None
    score = confidence.get("score", 0.0)
    if (abs(score - TIER_HIGH_THRESHOLD) <= ESCALATION_MARGIN
            or abs(score - TIER_MED_THRESHOLD) <= ESCALATION_MARGIN):
        return "tier_boundary"
    if (confidence.get("retrieval_score", 0.0) >= ESCALATION_RETRIEVAL_HIGH
            and confidence.get("citation_coverage", 1.0) <= ESCALATION_COVERAGE_LOW):
        return "high_retrieval_low_coverage"
    return None


def grounding_to_tier(grounding: int) -> str:
    """Map the judge's 1-5 grounding score onto the confidence tiers."""
    if grounding >= 4:
        return "high"
    if grounding == 3:
        return "medium"
    return "low"


class _FRDocChunk:
    """Shim so judge._chunk_context can render Federal Register documents as
    grounding context for forward-looking/blended answers (Part C)."""

    def __init__(self, d: dict):
        self.cfr_reference = d.get("fr_citation") or d.get("document_number") or "FR"
        self.chunk_text = (
            f"[status: {d.get('status')}] {d.get('title')}\n"
            f"Comments close: {d.get('comments_close_on') or 'n/a'} | "
            f"Effective: {d.get('effective_on') or 'n/a'} | "
            f"Affects: {', '.join(d.get('cfr_references') or [])}\n"
            f"{d.get('abstract') or ''}"
        )


def run_escalation(query: str, result: dict, chunks: list, reason: str) -> dict:
    """
    Judge one in-band answer inline. Returns the quality payload; the caller
    applies the tier override (judge wins) and the final security check.
    Forward-looking/blended answers add their Federal Register documents to
    the judge context and enforce the non-binding status-label rule.
    """
    forward = bool(result.get("forward_looking"))
    context = list(chunks)
    if forward:
        context += [_FRDocChunk(d) for d in result.get("fr_documents") or []]
    verdict = judge_grounding(
        query, result["plain_english"], context,
        legal_language=result.get("legal_language"),
        forward_looking=forward,
    )
    deterministic_tier = (result.get("confidence") or {}).get("tier")

    if verdict.error or verdict.grounding is None:
        # Fail open: keep the deterministic tier, surface the failure.
        return {
            "escalated": True,
            "escalation_reason": reason,
            "judge_grounding": None,
            "judge_tier": None,
            "judge_justification": None,
            "judge_error": verdict.error,
            "deterministic_tier": deterministic_tier,
            "agreement": None,
            "tier_overridden": False,
        }

    judge_tier = grounding_to_tier(verdict.grounding)
    return {
        "escalated": True,
        "escalation_reason": reason,
        "judge_grounding": verdict.grounding,
        "judge_tier": judge_tier,
        "judge_justification": verdict.justification,
        "judge_error": None,
        "deterministic_tier": deterministic_tier,
        "agreement": judge_tier == deterministic_tier,
        "tier_overridden": judge_tier != deterministic_tier,
    }
