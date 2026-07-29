#!/usr/bin/env python3
"""
optimize_confidence.py
----------------------
Grid search over confidence signal weights (alpha, beta, gamma) to maximize
Spearman rank correlation between the composite confidence score and LLM-judge
faithfulness scores from the evaluation harness.

Intended location in repo: eval/src/optimize_confidence.py

Usage:
    python eval/src/optimize_confidence.py \
        --eval-results eval/results/baseline_200q.json \
        --step 0.05 \
        --output eval/results/confidence_optimization.json

    # Finer search after identifying promising region:
    python eval/src/optimize_confidence.py \
        --eval-results eval/results/baseline_200q.json \
        --step 0.01 \
        --alpha-range 0.20 0.40 \
        --output eval/results/confidence_optimization_fine.json

Prerequisites:
    - Phase 9.1 Task 1 complete: retrieval_concentration must be present in
      eval result records (added to backend/query.py).
    - 200+ question eval run complete, results saved to JSON by evaluate.py.
    - pip install scipy numpy

Output:
    Console: top-10 weight combinations table + tier calibration table.
    JSON (if --output given): best weights, top-10, full calibration data.

What to do with the results:
    1. If best result has tier_ordering_correct=True AND rho >= 0.60:
       Update RETRIEVAL_WEIGHT, CITATION_WEIGHT, CONCENTRATION_WEIGHT
       constants in backend/confidence.py (or wherever weights are defined).
       Redeploy backend.

    2. If no result has tier_ordering_correct=True:
       The citation_coverage regex is the bottleneck. Proceed to Phase 9.1
       Task 3.4 (semantic grounding check) before updating weights.

    3. If best rho < 0.60 but tier ordering holds:
       Sample size may still be too small, OR retrieval_concentration is not
       adding signal. Try running without gamma (set --no-concentration flag)
       to compare two-component vs three-component performance.
"""

import json
import argparse
import os
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats


# ── Tier thresholds — must match backend/confidence.py ───────────────────────
TIER_HIGH   = 0.75
TIER_MEDIUM = 0.50
# Below TIER_MEDIUM is "low". "not_found" is a separate binary flag, not a tier.


# ── Data loading ──────────────────────────────────────────────────────────────

def load_eval_results(path: str) -> tuple[list[dict], int]:
    """
    Load evaluation result records from a JSON file produced by evaluate.py.

    Expected fields per record:
        question_id              str
        question                 str
        retrieval_score          float  # avg cosine similarity of top-3 chunks
        citation_coverage        float  # fraction of CFR § refs in generated
                                        # text that appear in retrieved chunk
                                        # metadata (regex-based, 0–1)
        retrieval_concentration  float  # 1 - normalized_stdev of top-K sims
                                        # (ADDED in Phase 9.1 Task 1, 0–1)
        faithfulness             float  # LLM judge score (0–1)
        legal_accuracy           float  # LLM judge score (0–1), optional
        tier                     str    # tier assigned under current weights
        not_found                bool   # True if no relevant content retrieved

    Accepts either a flat list of records OR the {"summary","results"} object that
    evaluate.py writes (nested confidence + generation_scores) — flattens to the
    fields above. not_found records are excluded.
    """
    with open(path) as f:
        data = json.load(f)

    raw = data["results"] if isinstance(data, dict) and "results" in data else data

    flat: list[dict] = []
    n_not_found = 0
    for r in raw:
        if "retrieval_score" in r and "faithfulness" in r:
            rec = r  # already flat
        else:
            conf = r.get("confidence") or {}
            gen = r.get("generation_scores") or {}
            rec = {
                "question_id": r.get("id"),
                "retrieval_score": conf.get("retrieval_score"),
                "citation_coverage": conf.get("citation_coverage"),
                "retrieval_concentration": conf.get("retrieval_concentration"),
                "faithfulness": gen.get("faithfulness"),
                "legal_accuracy": gen.get("legal_accuracy", 0.0),
                "tier": conf.get("tier"),
                "not_found": bool(gen.get("not_found")) or conf.get("tier") == "not_found",
            }
        if rec.get("not_found") or rec.get("faithfulness") is None:
            n_not_found += 1
            continue
        flat.append(rec)

    return flat, n_not_found


def load_from_db(run_ids: list[int] | None) -> tuple[list[dict], int]:
    """
    Phase 10 B.2 (conditional task): load fit records from the eval library —
    inference-time confidence components paired with the unified judge's
    grounding score as ground truth (grounding_norm, 0..1, replaces the old
    faithfulness target).

    Requires eval runs made after run_library_eval started persisting
    scores->'confidence' (the components). Uses the LATEST result per question
    (so pooled runs don't double-count); negatives, not_found, and judge
    errors are excluded.
    """
    import psycopg
    from dotenv import load_dotenv
    load_dotenv()

    run_filter = "AND r.run_id = ANY(%(runs)s)" if run_ids else ""
    with psycopg.connect(os.getenv("DATABASE_URL")) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT ON (r.question_id)
                   r.question_id::text, q.question_type, r.not_found, r.scores
            FROM eval_results r
            JOIN eval_questions q ON q.id = r.question_id
            WHERE q.question_type != 'negative' {run_filter}
            ORDER BY r.question_id, r.id DESC
            """,
            {"runs": run_ids},
        ).fetchall()

    records, skipped = [], 0
    strata: dict[str, int] = defaultdict(int)
    for qid, qtype, not_found, scores in rows:
        s = json.loads(scores) if isinstance(scores, str) else (scores or {})
        conf = s.get("confidence")
        g = s.get("grounding")
        if not_found or not conf or g is None:
            skipped += 1
            continue
        records.append({
            "question_id": qid,
            "question_type": qtype,
            "retrieval_score": conf["retrieval_score"],
            "citation_coverage": conf["citation_coverage"],
            "retrieval_concentration": conf["retrieval_concentration"],
            "faithfulness": (g - 1) / 4,          # judge grounding_norm is the target
            "legal_accuracy": 0.0,
            "tier": conf["tier"],
            "not_found": False,
        })
        strata[qtype] += 1

    print("  stratum mix:", dict(sorted(strata.items())))
    return records, skipped


def validate_fields(records: list[dict]) -> None:
    """Raise ValueError if required fields are missing from the first record."""
    required = [
        "retrieval_score",
        "citation_coverage",
        "retrieval_concentration",
        "faithfulness",
    ]
    missing = [f for f in required if f not in records[0]]
    if missing:
        raise ValueError(
            f"Eval result records are missing fields: {missing}\n\n"
            "retrieval_concentration must be added to the backend before running "
            "this script (Phase 9.1 Task 1 — backend/query.py).\n"
            "Re-run the 200-question evaluation after adding the field."
        )


# ── Score computation ─────────────────────────────────────────────────────────

def compute_composites(
    records: list[dict],
    alpha: float,
    beta: float,
    gamma: float,
) -> np.ndarray:
    """
    Compute composite confidence score for each record under the given weights.

    composite = alpha * retrieval_score
              + beta  * citation_coverage
              + gamma * retrieval_concentration

    All three components are in [0, 1]; composite is therefore also in [0, 1].
    """
    return np.array([
        alpha * r["retrieval_score"]
        + beta  * r["citation_coverage"]
        + gamma * r["retrieval_concentration"]
        for r in records
    ])


def assign_tiers(scores: np.ndarray) -> list[str]:
    """Assign tier labels (high / medium / low) based on composite scores."""
    tiers = []
    for s in scores:
        if s >= TIER_HIGH:
            tiers.append("high")
        elif s >= TIER_MEDIUM:
            tiers.append("medium")
        else:
            tiers.append("low")
    return tiers


# ── Calibration ───────────────────────────────────────────────────────────────

def tier_calibration(records: list[dict], tiers: list[str]) -> dict:
    """
    Compute per-tier statistics under a given weight combination.

    Returns a dict keyed by tier name ("high", "medium", "low"), each with:
        n                int    number of questions in this tier
        avg_faithfulness float  mean LLM-judge faithfulness score
        avg_legal_acc    float  mean LLM-judge legal accuracy score
    """
    by_tier: dict[str, list] = defaultdict(list)
    for record, tier in zip(records, tiers):
        by_tier[tier].append(record)

    result = {}
    for tier, recs in by_tier.items():
        result[tier] = {
            "n": len(recs),
            "avg_faithfulness": round(float(np.mean([r["faithfulness"] for r in recs])), 4),
            "avg_legal_acc":    round(float(np.mean([r.get("legal_accuracy", 0.0) for r in recs])), 4),
        }
    return result


def check_tier_ordering(calibration: dict) -> bool:
    """
    Return True if tier ordering holds: high > medium > low on avg_faithfulness.

    This is the Phase 9.1 success criterion. If no weight combination satisfies
    it, the citation_coverage component needs to be replaced with a semantic
    grounding check (Task 3.4) before the tiers can be shown to users.
    """
    ordered = ["high", "medium", "low"]
    present = [t for t in ordered if t in calibration]
    for i in range(len(present) - 1):
        if calibration[present[i]]["avg_faithfulness"] <= calibration[present[i + 1]]["avg_faithfulness"]:
            return False
    return True


# ── Grid search ───────────────────────────────────────────────────────────────

def grid_search(
    records: list[dict],
    step: float = 0.05,
    alpha_range: tuple[float, float] | None = None,
    beta_range: tuple[float, float] | None = None,
) -> list[dict]:
    """
    Exhaustive grid search over (alpha, beta, gamma) triples where
    alpha + beta + gamma = 1.0 and each is a multiple of `step`.

    Sorting priority:
        1. tier_ordering_correct = True first (the hard constraint)
        2. spearman_rho descending (the objective)

    This means the top result is always the highest-rho combination that also
    satisfies tier ordering. If no combination satisfies ordering, the top
    result is the highest-rho regardless.

    Args:
        records:     eval result records (not_found excluded)
        step:        grid granularity (0.05 default = 231 combinations,
                     0.01 = 5151 combinations)
        alpha_range: optional (min, max) to restrict alpha search space
        beta_range:  optional (min, max) to restrict beta search space
    """
    faithfulness = np.array([r["faithfulness"] for r in records])
    step_n = round(1.0 / step)   # integer grid size
    results = []

    for a_n in range(step_n + 1):
        alpha = a_n / step_n
        if alpha_range and not (alpha_range[0] <= alpha <= alpha_range[1]):
            continue

        for b_n in range(step_n - a_n + 1):
            beta = b_n / step_n
            if beta_range and not (beta_range[0] <= beta <= beta_range[1]):
                continue

            gamma = (step_n - a_n - b_n) / step_n

            composites = compute_composites(records, alpha, beta, gamma)
            rho, pval = stats.spearmanr(composites, faithfulness)

            tiers = assign_tiers(composites)
            calibration = tier_calibration(records, tiers)
            ordering_ok = check_tier_ordering(calibration)

            results.append({
                "alpha": round(alpha, 4),
                "beta":  round(beta, 4),
                "gamma": round(gamma, 4),
                "spearman_rho":          round(float(rho), 4),
                "spearman_pval":         round(float(pval), 6),
                "tier_ordering_correct": ordering_ok,
                "calibration":           calibration,
            })

    # Sort: ordering-correct first, then by rho descending
    results.sort(key=lambda r: (r["tier_ordering_correct"], r["spearman_rho"]), reverse=True)
    return results


# ── Output formatting ─────────────────────────────────────────────────────────

def print_results_table(results: list[dict], top_n: int = 10) -> None:
    """Print a formatted console table of the top-N weight combinations."""
    print(f"\n{'=' * 72}")
    print(f"  TOP {top_n} WEIGHT COMBINATIONS BY SPEARMAN RHO")
    print(f"{'=' * 72}")
    header = f"  {'#':>3}  {'alpha':>6}  {'beta':>6}  {'gamma':>6}  {'rho':>7}  {'p-val':>8}  {'ordering':>10}"
    print(header)
    print(f"  {'-'*3}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*8}  {'-'*10}")

    for i, r in enumerate(results[:top_n], 1):
        ordering = "OK  " if r["tier_ordering_correct"] else "FAIL"
        print(
            f"  {i:>3}  {r['alpha']:>6.2f}  {r['beta']:>6.2f}  {r['gamma']:>6.2f}  "
            f"{r['spearman_rho']:>7.4f}  {r['spearman_pval']:>8.5f}  {ordering:>10}"
        )

    best = results[0]
    print(
        f"\n  RECOMMENDED: alpha={best['alpha']:.2f}  beta={best['beta']:.2f}  "
        f"gamma={best['gamma']:.2f}  |  rho={best['spearman_rho']:.4f}  |  "
        f"ordering={'OK' if best['tier_ordering_correct'] else 'FAIL'}"
    )


def print_calibration_table(calibration: dict) -> None:
    """Print per-tier calibration statistics."""
    print(f"\n  TIER CALIBRATION (best weights):")
    print(f"  {'Tier':>8}  {'n':>4}  {'avg_faithfulness':>18}  {'avg_legal_acc':>14}")
    print(f"  {'-'*8}  {'-'*4}  {'-'*18}  {'-'*14}")
    for tier in ["high", "medium", "low"]:
        if tier in calibration:
            c = calibration[tier]
            print(
                f"  {tier:>8}  {c['n']:>4}  "
                f"{c['avg_faithfulness']:>18.4f}  "
                f"{c['avg_legal_acc']:>14.4f}"
            )
    print()


def print_ordering_guidance(results: list[dict]) -> None:
    """Print actionable guidance based on whether tier ordering is achievable."""
    any_ordering_ok = any(r["tier_ordering_correct"] for r in results)

    if results[0]["tier_ordering_correct"]:
        print("  [PASS] Tier ordering holds under best weights.")
        print("  Next step: update RETRIEVAL_WEIGHT, CITATION_WEIGHT, CONCENTRATION_WEIGHT")
        print("  in backend/confidence.py and redeploy.")

    elif any_ordering_ok:
        # There exists a valid ordering but it wasn't the top-rho result
        best_ordered = next(r for r in results if r["tier_ordering_correct"])
        print("  [WARN] Best rho result does not satisfy tier ordering.")
        print(f"  Best result WITH ordering: alpha={best_ordered['alpha']:.2f}  "
              f"beta={best_ordered['beta']:.2f}  gamma={best_ordered['gamma']:.2f}  "
              f"rho={best_ordered['spearman_rho']:.4f}")
        print("  Consider using this combination instead of the raw rho-maximizer.")

    else:
        print("  [FAIL] No weight combination produces correct tier ordering.")
        print("  The citation_coverage regex is penalizing grounded paraphrase.")
        print("  Required next step: Phase 9.1 Task 3.4 — semantic grounding check.")
        print("  Replace citation_coverage with semantic_grounding in the composite,")
        print("  then re-run this script.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grid search for optimal confidence signal weights.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--eval-results",
        help="Path to JSON eval results file produced by evaluate.py",
    )
    parser.add_argument(
        "--from-db", action="store_true",
        help="Phase 10 B.2: load records from eval_results/eval_questions with "
             "the unified judge's grounding score as the fit target",
    )
    parser.add_argument(
        "--runs", type=int, nargs="+",
        help="With --from-db: restrict to specific eval run ids",
    )
    parser.add_argument(
        "--step", type=float, default=0.05,
        help="Grid step size. Default 0.05 (231 combinations). Use 0.01 for fine search.",
    )
    parser.add_argument(
        "--alpha-range", type=float, nargs=2, metavar=("MIN", "MAX"),
        help="Restrict alpha search range, e.g. --alpha-range 0.20 0.40",
    )
    parser.add_argument(
        "--beta-range", type=float, nargs=2, metavar=("MIN", "MAX"),
        help="Restrict beta search range, e.g. --beta-range 0.40 0.70",
    )
    parser.add_argument(
        "--no-concentration", action="store_true",
        help="Run two-component search only (alpha + beta = 1.0, gamma = 0). "
             "Useful for comparing 2-component vs 3-component signal.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Path to write full results JSON (optional)",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="Number of top results to display (default: 10)",
    )
    args = parser.parse_args()

    # ── Load ──────────────────────────────────────────────────────────────────
    if args.from_db:
        print("Loading eval results from the DB library "
              f"(target = judge grounding{', runs ' + str(args.runs) if args.runs else ''})")
        records, n_not_found = load_from_db(args.runs)
    elif args.eval_results:
        print(f"Loading eval results from: {args.eval_results}")
        records, n_not_found = load_eval_results(args.eval_results)
    else:
        parser.error("provide --eval-results PATH or --from-db")
    print(f"  {len(records)} usable records loaded ({n_not_found} excluded)")

    if not records:
        print("No usable records — with --from-db this needs an eval run made "
              "after run_library_eval began persisting scores->'confidence'.")
        raise SystemExit(1)

    if len(records) < 30:
        print(f"\nWARNING: Only {len(records)} usable records. Phase 9.1 targets 200+.")
        print("Results may be unreliable at this sample size.\n")

    validate_fields(records)

    # ── Handle --no-concentration ─────────────────────────────────────────────
    if args.no_concentration:
        print("\nRunning two-component search (gamma forced to 0)...")
        # Temporarily zero out retrieval_concentration in records
        patched = [{**r, "retrieval_concentration": 0.0} for r in records]
        # Force gamma to 0 by restricting beta_range so a+b=1
        results = grid_search(
            patched,
            step=args.step,
            alpha_range=(0.0, 1.0),
            beta_range=(0.0, 1.0),
        )
        # Filter to gamma=0 results only
        results = [r for r in results if r["gamma"] == 0.0]
    else:
        # ── Full grid search ──────────────────────────────────────────────────
        step_n = round(1.0 / args.step)
        n_combinations = sum(
            1
            for a in range(step_n + 1)
            for _b in range(step_n - a + 1)
        )
        print(f"\nRunning grid search: step={args.step}, {n_combinations} combinations...")
        results = grid_search(
            records,
            step=args.step,
            alpha_range=tuple(args.alpha_range) if args.alpha_range else None,
            beta_range=tuple(args.beta_range) if args.beta_range else None,
        )

    # ── Print results ─────────────────────────────────────────────────────────
    print_results_table(results, top_n=args.top)
    print_calibration_table(results[0]["calibration"])
    print_ordering_guidance(results)

    # ── Save output ───────────────────────────────────────────────────────────
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        output_data = {
            "best": results[0],
            "top_10": results[:10],
            "summary": {
                "records_used":           len(records),
                "n_not_found_excluded":   n_not_found,
                "step":                   args.step,
                "total_combinations_evaluated": len(results),
                "any_ordering_correct":   any(r["tier_ordering_correct"] for r in results),
                "target_rho_met":         results[0]["spearman_rho"] >= 0.60,
            },
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nFull results written to: {args.output}")


if __name__ == "__main__":
    main()
