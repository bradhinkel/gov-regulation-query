#!/usr/bin/env python3
"""
Phase 9.1 — does semantic_grounding predict faithfulness better than the cheap
signals (which scored ρ≈0)? Re-scores each usable 200-q record's saved answer
with semantic_grounding (re-retrieving its context) and correlates with the saved
LLM-judge faithfulness.
"""
import json
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

from src.query import retrieve
from src.generate import semantic_grounding

results = json.load(open(PROJECT_ROOT / "eval/results/baseline_200.json"))["results"]
use = [r for r in results
       if r.get("confidence") and r["confidence"]["tier"] != "not_found"
       and r["generation_scores"].get("faithfulness") is not None
       and not r["generation_scores"].get("not_found")]

grounding, faith, rows = [], [], []
for i, r in enumerate(use):
    chunks, _ = retrieve(r["question"], top_k=10)
    sg = semantic_grounding(r["plain_english"], chunks)
    grounding.append(sg)
    faith.append(r["generation_scores"]["faithfulness"])
    rows.append({"id": r["id"], "grounding": sg, "faithfulness": faith[-1],
                 "citation_coverage": r["confidence"]["citation_coverage"]})
    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(use)}", flush=True)

rho, p = stats.spearmanr(grounding, faith)
print(f"\nsemantic_grounding vs faithfulness: spearman={rho:.3f} (p={p:.4f}), n={len(grounding)}")
print(f"grounding: mean {statistics.mean(grounding):.3f} std {statistics.pstdev(grounding):.3f}")
cc_rho, cc_p = stats.spearmanr([x["citation_coverage"] for x in rows], faith)
print(f"(reference) citation_coverage vs faithfulness: spearman={cc_rho:.3f} (p={cc_p:.4f})")

json.dump(rows, open(PROJECT_ROOT / "eval/results/grounding_corr.json", "w"), indent=2)
print("→ eval/results/grounding_corr.json")
