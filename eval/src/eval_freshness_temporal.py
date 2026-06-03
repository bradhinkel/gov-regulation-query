#!/usr/bin/env python3
"""
eval/src/eval_freshness_temporal.py — Phase 9.7 freshness + temporal evaluation.

Metrics (per the Phase 9 plan):
  - Staleness rate     : % of freshness queries that surface ANY archived chunk.
                         Target 0% (retrieval enforces status='active').
  - Intent accuracy    : is_temporal_query() vs a labeled set.
  - Temporal coverage  : % of "what changed?" queries that assemble a real
                         current-vs-archived comparison.
  - Temporal faithfulness (LLM judge): is the change summary grounded in the
                         provided current/prior texts? Target > 0.80.

Must run where the archived versions exist (the droplet). Needs OPENAI (embeddings)
and ANTHROPIC (judge) keys in the environment.

Usage:
    python eval/src/eval_freshness_temporal.py [--temporal-n 6] [--no-judge]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

import re

from src.query import retrieve, fetch_section_versions, DATABASE_URL
from src.generate import (
    is_temporal_query, generate_temporal, _strip_prefix, _client, GENERATION_MODEL,
)

# Labeled intent set (temporal=True should be detected).
INTENT_CASES = [
    ("what changed in organic certification rules", True),
    ("how have pesticide residue limits changed since 2024", True),
    ("recent changes to medical device classification", True),
    ("what's new in hospital conditions of participation", True),
    ("how was the definition of organic amended", True),
    ("what are the requirements for organic certification", False),
    ("define a Class II medical device", False),
    ("who must comply with OSHA fall protection rules", False),
    ("what is the THC limit for hemp", False),
    ("explain Medicare conditions of participation", False),
]

# Normal (non-temporal) queries — used for the staleness check.
FRESHNESS_QUERIES = [
    "What are the labeling requirements for organic produce?",
    "What is the definition of organic under USDA regulations?",
    "What are the Medicare conditions of participation for hospitals?",
    "What are the EPA emission standards for light-duty vehicles?",
    "What are OSHA fall protection requirements in construction?",
    "What are the medical certificate requirements for pilots?",
    "What are the hazardous materials labeling requirements for transport?",
    "What are the food additive safety requirements?",
]


def judge_temporal(query: str, answer: str, versions_text: str) -> float:
    """LLM judge: is the change summary grounded in the provided versions? 0..1."""
    prompt = (
        f"Question: {query}\n\nSection versions (CURRENT vs PRIOR):\n{versions_text[:6000]}\n\n"
        f"Answer to evaluate:\n{answer[:3000]}\n\n"
        "Does the answer accurately describe the change(s) between the prior and "
        "current text, using only what the versions support? Reply with a single "
        "number 0.0-1.0 (1.0 = fully accurate and grounded)."
    )
    try:
        r = _client.messages.create(
            model=GENERATION_MODEL, max_tokens=12,
            messages=[{"role": "user", "content": prompt}],
        )
        m = re.search(r"\d*\.?\d+", r.content[0].text)
        return max(0.0, min(1.0, float(m.group(0)))) if m else 0.0
    except Exception:
        return 0.0


def _versions_text(versions: dict) -> str:
    """Real CURRENT vs PRIOR text per changed section, for the judge."""
    parts = []
    for ref, v in versions.items():
        if not v["archived"] or not v["active"]:
            continue
        cur = " ".join(_strip_prefix(c.chunk_text) for c in v["active"])[:1500]
        pri = " ".join(_strip_prefix(c.chunk_text) for c in v["archived"])[:1500]
        parts.append(f"[{ref}]\nCURRENT: {cur}\nPRIOR: {pri}")
    return "\n\n".join(parts)


def run(temporal_n: int, judge: bool) -> None:
    conn = psycopg.connect(DATABASE_URL)

    # ── Intent accuracy ───────────────────────────────────────────────────────
    correct = sum(1 for q, lab in INTENT_CASES if is_temporal_query(q) == lab)
    intent_acc = correct / len(INTENT_CASES)

    # ── Staleness rate ────────────────────────────────────────────────────────
    stale_hits = 0
    for q in FRESHNESS_QUERIES:
        chunks, _ = retrieve(q, top_k=10)
        ids = [c.chunk_id for c in chunks]
        if ids:
            n = conn.execute(
                "SELECT count(*) FROM chunks WHERE id = ANY(%s::uuid[]) AND status <> 'active'",
                (ids,),
            ).fetchone()[0]
            stale_hits += 1 if n else 0
    staleness_rate = stale_hits / len(FRESHNESS_QUERIES)

    # ── Temporal: data-driven from sections that actually changed ─────────────
    # Sample typical-size amended sections (1-6 chunks), one per part for variety —
    # avoids over-weighting huge enumerated list sections (e.g. drug schedules),
    # which are an acknowledged harder case for the small model.
    changed = conn.execute(
        """
        SELECT DISTINCT ON (part_number) cfr_reference, section_heading
        FROM (
            SELECT cfr_reference, section_heading, part_number, count(*) AS n
            FROM chunks
            WHERE status='archived' AND section_heading IS NOT NULL
            GROUP BY cfr_reference, section_heading, part_number
            HAVING count(*) BETWEEN 1 AND 6
        ) s
        ORDER BY part_number, cfr_reference
        LIMIT %s
        """,
        (temporal_n,),
    ).fetchall()

    temporal_results = []
    for cfr_ref, heading in changed:
        q = f"What changed in {heading}?"
        if not is_temporal_query(q):
            temporal_results.append({"q": q, "detected": False, "compared": False, "faith": None})
            continue
        chunks, _ = retrieve(q, top_k=10)
        # ensure the changed section is in scope even if retrieval ranked it lower
        refs = list({c.cfr_reference for c in chunks if c.cfr_reference} | {cfr_ref})
        versions = fetch_section_versions(refs)
        gen = generate_temporal(q, versions, chunks)
        compared = gen is not None
        faith = None
        if compared and judge:
            faith = judge_temporal(q, gen.response.plain_english, _versions_text(versions))
        temporal_results.append({"q": q, "detected": True, "compared": compared,
                                 "faith": faith,
                                 "answer_len": len(gen.response.plain_english) if gen else 0})

    compared_n = sum(1 for r in temporal_results if r["compared"])
    coverage = compared_n / len(temporal_results) if temporal_results else 0.0
    faiths = [r["faith"] for r in temporal_results if r["faith"] is not None]
    avg_faith = sum(faiths) / len(faiths) if faiths else None

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n=== Phase 9.7 — Freshness & Temporal ===")
    print(f"Intent accuracy        : {intent_acc:.0%} ({correct}/{len(INTENT_CASES)})")
    print(f"Staleness rate         : {staleness_rate:.0%}  (target 0%; {stale_hits}/{len(FRESHNESS_QUERIES)} queries hit archived)")
    print(f"Temporal coverage      : {coverage:.0%}  ({compared_n}/{len(temporal_results)} produced a comparison)")
    if avg_faith is not None:
        print(f"Temporal faithfulness  : {avg_faith:.2f}  (target > 0.80, n={len(faiths)})")
    print("\nTemporal cases:")
    for r in temporal_results:
        print(f"  detected={r['detected']} compared={r['compared']} "
              f"faith={r['faith']} | {r['q']}")

    out = {
        "intent_accuracy": round(intent_acc, 4),
        "staleness_rate": round(staleness_rate, 4),
        "temporal_coverage": round(coverage, 4),
        "temporal_faithfulness": round(avg_faith, 4) if avg_faith is not None else None,
        "n_changed_sections_available": len(changed),
    }
    results_dir = PROJECT_ROOT / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "freshness_temporal.json").write_text(json.dumps(out, indent=2))
    print(f"\nSummary → eval/results/freshness_temporal.json\n{json.dumps(out, indent=2)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--temporal-n", type=int, default=6)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()
    run(args.temporal_n, judge=not args.no_judge)
