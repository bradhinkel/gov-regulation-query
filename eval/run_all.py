"""
eval/run_all.py — Run all evaluation configs and print a comparison table.

Usage:
    python eval/run_all.py                  # run all configs
    python eval/run_all.py --limit 10       # run each config on 10 questions
    python eval/run_all.py --retrieval-only # skip generation, retrieval metrics only
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIGS_DIR = PROJECT_ROOT / "eval" / "configs"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"


def run_all(limit: int | None, retrieval_only: bool, config_names: list[str] | None):
    from eval.src.evaluate import run_evaluation

    config_paths = []
    if config_names:
        for name in config_names:
            p = CONFIGS_DIR / f"{name}.yaml"
            if not p.exists():
                print(f"[error] Config not found: {p}")
                sys.exit(1)
            config_paths.append(p)
    else:
        config_paths = sorted(CONFIGS_DIR.glob("*.yaml"))

    if not config_paths:
        print("[error] No configs found in eval/configs/")
        sys.exit(1)

    summaries = []
    for config_path in config_paths:
        print(f"\n{'='*60}")
        print(f"Running: {config_path.name}")
        print(f"{'='*60}")
        output = run_evaluation(str(config_path), limit=limit, skip_generation=retrieval_only)
        summaries.append(output["summary"])

    # Comparison table
    print(f"\n{'='*70}")
    print("COMPARISON TABLE")
    print(f"{'='*70}")

    header_fmt = "{:<25} {:>8} {:>8} {:>8} {:>8}"
    row_fmt    = "{:<25} {:>8} {:>8} {:>8} {:>8}"

    if retrieval_only:
        print(header_fmt.format("Config", "MRR", "NDCG@k", "Prec@k", "Rec@k"))
        print("-" * 70)
        for s in summaries:
            r = s["retrieval"]
            print(row_fmt.format(
                s["config"][:25],
                f"{r['avg_mrr'] or 0:.4f}",
                f"{r['avg_ndcg_at_k'] or 0:.4f}",
                f"{r['avg_precision_at_k'] or 0:.4f}",
                f"{r['avg_recall_at_k'] or 0:.4f}",
            ))
    else:
        print(header_fmt.format("Config", "Faith", "LegalAcc", "CitAcc", "Tokens"))
        print("-" * 70)
        for s in summaries:
            g = s["generation"]
            t = s["tokens"]
            print(row_fmt.format(
                s["config"][:25],
                f"{g['avg_faithfulness'] or 0:.4f}",
                f"{g['avg_legal_accuracy'] or 0:.4f}",
                f"{g['avg_citation_accuracy'] or 0:.4f}",
                str(t["total_input"] + t["total_output"]),
            ))

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all eval configs")
    parser.add_argument("--limit", type=int, help="Limit questions per config")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--configs", nargs="+", help="Specific config names (without .yaml)")
    args = parser.parse_args()

    run_all(
        limit=args.limit,
        retrieval_only=args.retrieval_only,
        config_names=args.configs,
    )
