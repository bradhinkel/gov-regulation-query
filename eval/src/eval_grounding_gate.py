"""
eval/src/eval_grounding_gate.py — Phase 10 B.2: the hallucination-gate metric.

Validates that the inline judge catches ungrounded answers before delivery.
Builds a seeded set of deliberately ungrounded answers from the library's own
eval_results (no generation cost — judge calls only), two corruption modes:

  mismatch — the (good) answer to a DIFFERENT question, presented against this
             question's retrieved context. Fully ungrounded.
  mutation — the question's own good answer with numerics incremented and
             obligation polarity flipped (must->may, at least->at most).
             Subtly ungrounded: the harder, more realistic case.

Caught (docx: "downgraded or flagged before delivery") mirrors the real
delivery path end to end:
  1. deterministic tier of the corrupted answer (compute_confidence) — an
     answer scored "low" is already flagged to the user;
  2. escalation band membership (escalation_reason) — decides whether the
     judge runs at all;
  3. judge override — caught if the judge tier is BELOW the deterministic
     tier (downgrade) or is "low".
system_catch = det_low OR (in_band AND judge_downgrade). Also reports the
judge-only catch rate for calibration. Target: >=90% system catch rate
(docx B.6 — the part's primary success criterion).

Usage:
    python eval/src/eval_grounding_gate.py --n 20        # 20 per mode (~40 judge calls)
"""

import argparse
import os
import random
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.query import retrieve
from src.judge import judge_grounding, JUDGE_MODEL
from src.generate import compute_confidence, QueryResponse
from src.escalation import escalation_reason, grounding_to_tier

_TIER_RANK = {"low": 0, "medium": 1, "high": 2}

DATABASE_URL = os.getenv("DATABASE_URL")
TOP_K = int(os.getenv("RAG_TOP_K", "10"))


def load_good_answers(conn, limit: int) -> list[dict]:
    """Anchored questions + their high-composite answers from the latest full run."""
    rows = conn.execute(
        """
        SELECT q.id::text, q.question, q.question_type, r.plain_english
        FROM eval_results r
        JOIN eval_questions q ON q.id = r.question_id
        WHERE r.run_id = (SELECT max(id) FROM eval_runs WHERE scope = 'full')
          AND q.question_type NOT IN ('negative')
          AND r.composite >= 0.8
          AND r.plain_english IS NOT NULL
        ORDER BY q.id
        """
    ).fetchall()
    cases = [dict(zip(("id", "question", "question_type", "answer"), r)) for r in rows]
    random.Random(42).shuffle(cases)
    return cases[:limit]


_NUM_RE = re.compile(r"(?<![\d.§])(\d+)(?![\d.]*\s*CFR)")
_POLARITY = [
    (re.compile(r"\bmust\b"), "may"), (re.compile(r"\bshall\b"), "may"),
    (re.compile(r"\bat least\b"), "at most"),
    (re.compile(r"\bnot less than\b"), "not more than"),
    (re.compile(r"\bprohibited\b"), "permitted"),
    (re.compile(r"\brequired\b"), "optional"),
]


def mutate(answer: str) -> str | None:
    """Flip obligations and shift numerics; None if nothing mutated."""
    out, changed = answer, False
    for pat, repl in _POLARITY:
        out2 = pat.sub(repl, out, count=2)
        changed |= out2 != out
        out = out2

    def bump(m: re.Match) -> str:
        return str(int(m.group(1)) * 3 + 7)

    out2 = _NUM_RE.sub(bump, out, count=4)
    changed |= out2 != out
    return out2 if changed else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="seeded cases per mode")
    args = ap.parse_args()

    conn = psycopg.connect(DATABASE_URL)
    cases = load_good_answers(conn, args.n * 2)
    conn.close()
    if len(cases) < 4:
        print("[gate] not enough high-composite answers in the latest full run")
        return 1

    seeded = []
    # mismatch: rotate answers by half the list so pairs are far apart
    half = len(cases) // 2
    for i, c in enumerate(cases[:args.n]):
        donor = cases[(i + half) % len(cases)]
        seeded.append({**c, "mode": "mismatch", "bad_answer": donor["answer"]})
    for c in cases[:args.n]:
        mut = mutate(c["answer"])
        if mut:
            seeded.append({**c, "mode": "mutation", "bad_answer": mut})

    print(f"[gate] judging {len(seeded)} seeded ungrounded answers "
          f"(judge={JUDGE_MODEL}, top_k={TOP_K})")
    stats: dict[str, list] = {}
    judge_flags: dict[str, list] = {}
    in_tok = out_tok = 0
    for i, s in enumerate(seeded):
        chunks, _ = retrieve(s["question"], top_k=TOP_K)

        # 1. Deterministic pass, exactly as production scores the answer.
        fake = QueryResponse(plain_english=s["bad_answer"], legal_language="",
                             citations=[], strategy_used="seeded")
        conf = compute_confidence(fake, chunks)
        det_tier = conf.tier
        conf_dict = {"tier": det_tier, "score": conf.score,
                     "retrieval_score": conf.retrieval_score,
                     "citation_coverage": conf.citation_coverage}
        det_low = det_tier == "low"

        # 2. Band membership decides whether the judge runs.
        in_band = escalation_reason(conf_dict) is not None

        # 3. Judge (always run here so the judge-only rate is measurable).
        v = judge_grounding(s["question"], s["bad_answer"], chunks)
        in_tok += v.input_tokens
        out_tok += v.output_tokens
        if v.error or v.grounding is None:
            print(f"  [{i+1}/{len(seeded)}] {s['mode']:<9} JUDGE ERROR: {v.error}")
            stats.setdefault(s["mode"], []).append(None)
            continue
        judge_tier = grounding_to_tier(v.grounding)
        judge_downgrade = (_TIER_RANK[judge_tier] < _TIER_RANK[det_tier]
                           or judge_tier == "low")
        caught = det_low or (in_band and judge_downgrade)
        stats.setdefault(s["mode"], []).append(caught)
        judge_flags.setdefault(s["mode"], []).append(judge_downgrade)
        print(f"  [{i+1}/{len(seeded)}] {s['mode']:<9} det={det_tier:<6} "
              f"band={'y' if in_band else 'n'} judge={v.grounding} "
              f"{'CAUGHT' if caught else 'MISSED'}  {s['question'][:50]}")

    print("\n[gate] system catch = det_low OR (in_band AND judge downgrade/low):")
    all_flags = []
    for mode, flags in sorted(stats.items()):
        ok = [f for f in flags if f is not None]
        all_flags += ok
        jf = judge_flags.get(mode, [])
        jrate = sum(jf) / len(jf) if jf else 0.0
        rate = sum(ok) / len(ok) if ok else 0.0
        print(f"    {mode:<9} n={len(ok):<3} system_catch={rate:.1%}  "
              f"judge_only={jrate:.1%}")
    overall = sum(all_flags) / len(all_flags) if all_flags else 0.0
    print(f"    overall   n={len(all_flags):<3} system_catch={overall:.1%}  "
          f"target>=90% {'PASS' if overall >= 0.9 else 'FAIL'}")
    print(f"    tokens: in={in_tok} out={out_tok}")
    return 0 if overall >= 0.9 else 2


if __name__ == "__main__":
    sys.exit(main())
