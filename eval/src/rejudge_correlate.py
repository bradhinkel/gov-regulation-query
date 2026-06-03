#!/usr/bin/env python3
"""
Phase 9.1 — the single-call Haiku faithfulness judge proved unreliable (it scored
verifiably-correct, ground-truth-matching answers 0.2-0.3). Re-judge the saved
200-q answers with a stronger judge (Sonnet) against the human/seed ground-truth
reference, then re-correlate the confidence signals with the cleaner target. If a
signal now tracks quality, a reweighting is justified; if not, the signals are
genuinely weak.
"""
import json
import os
import re
import statistics
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-sonnet-4-6")
_client = anthropic.Anthropic()

JUDGE_SYSTEM = (
    "You are grading a federal-regulation answer against a known-correct reference "
    "answer. Score CORRECTNESS from 0.0 to 1.0: 1.0 = states the same regulatory "
    "facts/requirements as the reference (extra correct detail is fine); 0.5 = "
    "partially correct or incomplete; 0.0 = wrong or contradicts the reference. "
    "Reply with ONLY the number."
)


def judge(question: str, reference: str, answer: str) -> float:
    prompt = (f"Question: {question}\n\nReference answer:\n{reference}\n\n"
              f"System answer:\n{answer[:2500]}\n\nCorrectness score (0.0-1.0):")
    try:
        r = _client.messages.create(model=JUDGE_MODEL, max_tokens=8,
                                    system=JUDGE_SYSTEM,
                                    messages=[{"role": "user", "content": prompt}])
        m = re.search(r"\d*\.?\d+", r.content[0].text)
        return max(0.0, min(1.0, float(m.group(0)))) if m else None
    except Exception as e:
        print("  judge error:", e)
        return None


def main():
    gc = {r["id"]: r for r in json.load(open(PROJECT_ROOT / "eval/results/grounding_corr.json"))}
    res = json.load(open(PROJECT_ROOT / "eval/results/baseline_200.json"))["results"]
    use = [r for r in res
           if r.get("confidence") and r["confidence"]["tier"] != "not_found"
           and not r["generation_scores"].get("not_found")
           and r.get("ground_truth")]

    rows = []
    for i, r in enumerate(use):
        score = judge(r["question"], r["ground_truth"], r["plain_english"])
        if score is None:
            continue
        c = r["confidence"]
        rows.append({
            "id": r["id"],
            "correctness": score,
            "old_faith": r["generation_scores"].get("faithfulness"),
            "retrieval": c["retrieval_score"],
            "citation": c["citation_coverage"],
            "concentration": c["retrieval_concentration"],
            "grounding": gc.get(r["id"], {}).get("grounding"),
        })
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(use)}", flush=True)

    json.dump(rows, open(PROJECT_ROOT / "eval/results/rejudge.json", "w"), indent=2)
    y = [x["correctness"] for x in rows]
    print(f"\nn={len(rows)}  correctness mean {statistics.mean(y):.3f} std {statistics.pstdev(y):.3f}")
    print(f"agreement w/ old Haiku faithfulness: spearman={stats.spearmanr(y,[x['old_faith'] for x in rows])[0]:.3f}")
    print("\nSignal vs NEW correctness (Sonnet, vs reference):")
    for k in ["retrieval", "citation", "grounding", "concentration"]:
        xs = [x[k] for x in rows if x[k] is not None]
        ys = [x["correctness"] for x in rows if x[k] is not None]
        rho, p = stats.spearmanr(xs, ys)
        print(f"  {k:14}: spearman={rho:+.3f} (p={p:.4f})")
    print("\n→ eval/results/rejudge.json")


if __name__ == "__main__":
    main()
