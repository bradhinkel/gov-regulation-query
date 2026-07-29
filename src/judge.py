"""
src/judge.py — Phase 10 Part A: the unified grounding judge.

One judge, one rubric, two modes:
  - offline (eval runs): scores an answer against the retrieved context AND the
    library's ground-truth reference — adds a correctness score.
  - inline (Part B escalation): scores against retrieved context only.

This replaces the three inconsistent scorers that predate it (the eval judge in
eval/src/evaluate.py, the saturating per-sentence semantic_grounding call, and
the citation_coverage regex as a grounding proxy). Sharing the rubric is what
makes the longitudinal quality score commensurable with per-answer verdicts.

Model: JUDGE_MODEL (default Sonnet — the Phase 9.1 finding is that a Haiku
judge is too noisy to serve as ground truth).
"""

import json
import os
import re
from dataclasses import dataclass

import anthropic

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-4-6")
JUDGE_MAX_TOKENS = 512

# Structured output schema — guarantees a parseable verdict (assistant prefill
# is not supported on the 4.6+ model family; output_config.format is the
# replacement). Range checks beyond enum aren't supported in the schema
# subset, so correctness is clamped client-side in _parse_verdict.
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "grounding": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "completeness": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "correctness": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "justification": {"type": "string"},
    },
    "required": ["grounding", "completeness", "correctness", "justification"],
    "additionalProperties": False,
}

_client = anthropic.Anthropic()

_JUDGE_SYSTEM = """\
You are an expert evaluator of a federal-regulation question-answering system.
You judge one answer against the regulatory context that was retrieved for it.

Score these dimensions:
- grounding (integer 1-5): Is every claim in the answer supported by the
  retrieved context? 5 = every claim supported (verbatim or faithful
  paraphrase); 3 = mostly supported with minor unsupported additions;
  1 = key claims are not in the context (hallucinated). Judge SEMANTIC support:
  a correct paraphrase that does not restate the citation is still grounded.
- completeness (integer 1-5): Given what the context contains, does the answer
  fully address the question? 5 = complete; 1 = misses most of it.

If a ground-truth reference answer is provided, also score:
- correctness (float 0.0-1.0): Does the answer agree with the reference on the
  substantive regulatory facts (requirements, thresholds, dates, scope)?
  Wording differences do not matter; factual disagreement does.

Respond with ONLY a JSON object:
{"grounding": <int>, "completeness": <int>, "correctness": <float or null>,
 "justification": "<2-3 sentences: what is or is not supported, citing the decisive claim>"}"""


@dataclass
class JudgeVerdict:
    grounding: int | None          # 1-5; None on judge failure
    completeness: int | None       # 1-5
    correctness: float | None      # 0-1, offline mode only
    justification: str
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None

    @property
    def grounding_norm(self) -> float | None:
        """Grounding mapped to 0..1 for composites."""
        return None if self.grounding is None else (self.grounding - 1) / 4


def _chunk_context(chunks: list, max_chars: int = 14000) -> str:
    parts = []
    for c in chunks:
        cite = c.citation_string() if hasattr(c, "citation_string") else (
            getattr(c, "cfr_reference", "") or "")
        text = getattr(c, "chunk_text", "") or ""
        parts.append(f"[{cite}]\n{text}")
    return "\n\n".join(parts)[:max_chars]


def _parse_verdict(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip().rsplit("```", 1)[0].strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in judge output: {raw[:200]}")
    data = json.loads(m.group(0))
    g = int(data["grounding"])
    comp = int(data["completeness"])
    if not (1 <= g <= 5 and 1 <= comp <= 5):
        raise ValueError(f"scores out of range: grounding={g} completeness={comp}")
    corr = data.get("correctness")
    if corr is not None:
        corr = min(1.0, max(0.0, float(corr)))
    return {"grounding": g, "completeness": comp, "correctness": corr,
            "justification": str(data.get("justification", "")).strip()}


# Phase 10 Part C: appended to the rubric when judging forward-looking
# answers. A proposed rule presented as binding is the critical failure mode.
_FORWARD_CLAUSE = """

This answer discusses PROPOSED or upcoming rules (Federal Register documents).
Additional hard rule: every claim presenting proposed or pending content must
carry an explicit non-binding status label (e.g. "PROPOSED", "comment period",
"not yet in effect", "pending"). If ANY proposed-content claim reads as if it
were current binding law — no status label — cap grounding at 2 and say so in
the justification."""


def judge_grounding(
    question: str,
    answer: str,
    chunks: list,
    *,
    legal_language: str | None = None,
    reference: str | None = None,
    model: str | None = None,
    forward_looking: bool = False,
) -> JudgeVerdict:
    """
    Judge one answer. `reference` present → offline mode (adds correctness).
    `forward_looking` → enforce non-binding status labels (Part C).
    Never raises: a judge failure returns a verdict with error set and None
    scores; the caller decides fail-open vs fail-closed.
    """
    sections = [
        f"Question:\n{question}",
        f"Retrieved regulatory context:\n{_chunk_context(chunks)}",
        f"Answer under evaluation (plain English):\n{answer}",
    ]
    if legal_language:
        sections.append(f"Answer under evaluation (legal register):\n{legal_language[:4000]}")
    if reference:
        sections.append(f"Ground-truth reference answer:\n{reference}")
    else:
        sections.append("No ground-truth reference is available; set correctness to null.")

    system = _JUDGE_SYSTEM + (_FORWARD_CLAUSE if forward_looking else "")
    in_tok = out_tok = 0
    last_err = ""
    for attempt in range(2):
        try:
            r = _client.messages.create(
                model=model or JUDGE_MODEL,
                max_tokens=JUDGE_MAX_TOKENS,
                temperature=0,
                system=system,
                # extra_body: installed SDK predates the typed output_config kwarg;
                # the API accepts it regardless.
                extra_body={"output_config": {"format": {"type": "json_schema",
                                                         "schema": _VERDICT_SCHEMA}}},
                messages=[{"role": "user", "content": "\n\n".join(sections)}],
            )
            in_tok += r.usage.input_tokens
            out_tok += r.usage.output_tokens
            parsed = _parse_verdict(r.content[0].text if r.content else "")
            return JudgeVerdict(**parsed, input_tokens=in_tok, output_tokens=out_tok)
        except (anthropic.APIError, ValueError, KeyError, json.JSONDecodeError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
    return JudgeVerdict(grounding=None, completeness=None, correctness=None,
                        justification="", input_tokens=in_tok, output_tokens=out_tok,
                        error=last_err)
