"""
eval/src/run_library_eval.py — Phase 10 Part A: scheduled eval over the DB library.

Reads eval_questions, runs the production pipeline (retrieve → generate), scores
with the unified grounding judge (src/judge.py, offline mode), and persists the
run to eval_runs / eval_results. Two aggregate quality scores per run:

  composite_core — stable core only (times_refreshed = 0): the longitudinal
                   trend line, comparable across runs.
  composite_all  — every active question in scope: the representative snapshot.

Per-question composite:
  anchored : 0.4·correctness + 0.4·grounding + 0.2·completeness (judge, 0..1)
             (not_found on an anchored question scores 0.0)
  negative : 1.0 if the system said not_found, else 0.0

Cost cap: the run aborts (status 'aborted_cost_cap', partial results kept) if
total generation+judge tokens exceed EVAL_TOKEN_BUDGET.

Usage:
    python eval/src/run_library_eval.py --scope core          # weekly (post-sync)
    python eval/src/run_library_eval.py --scope full          # monthly
    python eval/src/run_library_eval.py --scope core --limit 5   # smoke test
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.query import retrieve
from src.generate import generate, GENERATION_MODEL
from src.judge import judge_grounding, JUDGE_MODEL
from eval.src.evaluate import retrieval_metrics

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag",
)
TOP_K = int(os.getenv("RAG_TOP_K", "6"))
TOKEN_BUDGET = int(os.getenv("EVAL_TOKEN_BUDGET", "3000000"))

CORE_SQL = "status = 'active' AND times_refreshed = 0 AND origin = 'generated'"


def load_questions(conn, scope: str, limit: int | None) -> list[dict]:
    where = CORE_SQL if scope == "core" else "status = 'active'"
    rows = conn.execute(
        f"""
        SELECT id::text, question, question_type, ground_truth, ground_truth_reference,
               anchor_title, ({CORE_SQL}) AS is_core
        FROM eval_questions WHERE {where}
        ORDER BY question_type, anchor_title NULLS LAST, created_at
        {'LIMIT %s' % int(limit) if limit else ''}
        """
    ).fetchall()
    cols = ("id", "question", "question_type", "ground_truth",
            "ground_truth_reference", "anchor_title", "is_core")
    return [dict(zip(cols, r)) for r in rows]


def evaluate_question(q: dict, top_k: int) -> dict:
    """Run one question through the production pipeline and score it."""
    chunks, timing = retrieve(q["question"], top_k=top_k)
    gen = generate(q["question"], chunks, strategy="sequential", model=GENERATION_MODEL)
    qr = gen.response
    tokens = {"input": gen.input_tokens, "output": gen.output_tokens}

    if q["question_type"] == "negative":
        # A negative must be refused; the judge isn't needed (or billed).
        composite = 1.0 if qr.not_found else 0.0
        return {
            "composite": composite, "not_found": qr.not_found, "tokens": tokens,
            "plain_english": None if qr.not_found else qr.plain_english,
            "scores": {"negative_pass": composite == 1.0,
                       "confidence_tier": gen.confidence.tier if gen.confidence else None},
        }

    ret = retrieval_metrics(chunks, q.get("ground_truth_reference") or "", top_k)
    if qr.not_found:
        return {
            "composite": 0.0, "not_found": True, "tokens": tokens,
            "plain_english": None,
            "scores": {"retrieval": ret, "judge_error": None,
                       "confidence_tier": gen.confidence.tier if gen.confidence else None},
        }

    verdict = judge_grounding(
        q["question"], qr.plain_english, chunks,
        legal_language=qr.legal_language, reference=q.get("ground_truth"),
    )
    tokens["input"] += verdict.input_tokens
    tokens["output"] += verdict.output_tokens

    if verdict.error or verdict.grounding is None:
        composite = None  # excluded from aggregates; counted as judge_error
    else:
        corr = verdict.correctness if verdict.correctness is not None else verdict.grounding_norm
        composite = round(
            0.4 * corr + 0.4 * verdict.grounding_norm
            + 0.2 * ((verdict.completeness - 1) / 4), 4)

    return {
        "composite": composite, "not_found": False, "tokens": tokens,
        "plain_english": qr.plain_english,
        "scores": {
            "grounding": verdict.grounding, "completeness": verdict.completeness,
            "correctness": verdict.correctness, "justification": verdict.justification,
            "judge_error": verdict.error, "retrieval": ret,
            "confidence_tier": gen.confidence.tier if gen.confidence else None,
        },
    }


def _mean(vals: list) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def aggregate(results: list[dict]) -> dict:
    """Per-title / per-stratum breakdown + the variance precondition metric."""
    by_stratum: dict[str, list] = {}
    by_title: dict[str, list] = {}
    groundings = []
    g_by_stratum: dict[str, list] = {}
    for r in results:
        by_stratum.setdefault(r["q"]["question_type"], []).append(r["composite"])
        if r["q"]["anchor_title"]:
            by_title.setdefault(str(r["q"]["anchor_title"]), []).append(r["composite"])
        g = r["scores"].get("grounding")
        if g is not None:
            groundings.append((g - 1) / 4)
            g_by_stratum.setdefault(r["q"]["question_type"], []).append((g - 1) / 4)

    def _std(vals: list) -> float | None:
        return round(statistics.pstdev(vals), 4) if len(vals) > 1 else None

    negatives = [r for r in results if r["q"]["question_type"] == "negative"]
    return {
        "per_stratum": {s: {"n": len(v), "composite": _mean(v),
                            "grounding_mean": _mean(g_by_stratum.get(s, [])),
                            "grounding_std": _std(g_by_stratum.get(s, []))}
                        for s, v in sorted(by_stratum.items())},
        "per_title": {t: {"n": len(v), "composite": _mean(v)}
                      for t, v in sorted(by_title.items(), key=lambda kv: int(kv[0]))},
        "retrieval": {
            "avg_mrr": _mean([r["scores"].get("retrieval", {}).get("mrr")
                              for r in results if r["scores"].get("retrieval")]),
            "avg_ndcg": _mean([r["scores"].get("retrieval", {}).get("ndcg_at_k")
                               for r in results if r["scores"].get("retrieval")]),
        },
        "negatives": {
            "n": len(negatives),
            "not_found_accuracy": _mean([r["composite"] for r in negatives]),
        },
        "judge_errors": sum(1 for r in results if r["scores"].get("judge_error")),
        # Phase 10 B.2 precondition: calibration needs non-zero grounding variance.
        "grounding_std": round(statistics.pstdev(groundings), 4) if len(groundings) > 1 else None,
    }


def run(scope: str, limit: int | None, top_k: int, budget: int) -> int:
    conn = psycopg.connect(DATABASE_URL)
    try:
        questions = load_questions(conn, scope, limit)
        if not questions:
            print("[eval] library is empty — run library.py seed first")
            return 1
        print(f"[eval] scope={scope}  questions={len(questions)}  top_k={top_k}  "
              f"gen={GENERATION_MODEL}  judge={JUDGE_MODEL}  budget={budget} tokens")

        results, in_tok, out_tok = [], 0, 0
        status = "ok"
        t0 = time.time()
        for i, q in enumerate(questions):
            if in_tok + out_tok > budget:
                status = "aborted_cost_cap"
                print(f"[eval] TOKEN BUDGET EXCEEDED at question {i} — aborting, "
                      f"keeping {len(results)} partial results")
                break
            print(f"  [{i+1}/{len(questions)}] {q['question_type']:<16} {q['question'][:60]}...")
            try:
                r = evaluate_question(q, top_k)
            except Exception as exc:  # noqa: BLE001 — one bad question shouldn't kill the run
                print(f"    [warn] failed: {exc}")
                r = {"composite": None, "not_found": None, "tokens": {"input": 0, "output": 0},
                     "plain_english": None, "scores": {"judge_error": f"pipeline: {exc}"}}
            r["q"] = q
            results.append(r)
            in_tok += r["tokens"]["input"]
            out_tok += r["tokens"]["output"]

        agg = aggregate(results)
        composite_all = _mean([r["composite"] for r in results])
        composite_core = _mean([r["composite"] for r in results if r["q"]["is_core"]])
        num_core = sum(1 for r in results if r["q"]["is_core"])

        scores = {**agg, "config": {"top_k": top_k, "generation_model": GENERATION_MODEL,
                                    "judge_model": JUDGE_MODEL, "scope": scope,
                                    "limit": limit, "duration_s": round(time.time() - t0, 1)}}

        run_id = conn.execute(
            """
            INSERT INTO eval_runs (scope, status, num_questions, num_core,
                                   composite_all, composite_core, scores,
                                   input_tokens, output_tokens)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (scope, status, len(results), num_core, composite_all, composite_core,
             json.dumps(scores), in_tok, out_tok),
        ).fetchone()[0]
        with conn.cursor() as cur:
            for r in results:
                cur.execute(
                    """
                    INSERT INTO eval_results (run_id, question_id, is_core, composite,
                                              not_found, scores, plain_english)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (run_id, r["q"]["id"], r["q"]["is_core"], r["composite"],
                     r["not_found"], json.dumps(r["scores"]), r["plain_english"]),
                )
        conn.commit()

        print(f"\n[eval] run #{run_id} ({status})  composite_all={composite_all}  "
              f"composite_core={composite_core} (n={num_core})")
        for s, v in scores["per_stratum"].items():
            print(f"    {s:<18} n={v['n']:<3} composite={v['composite']}  "
                  f"grounding={v['grounding_mean']} ±{v['grounding_std']}")
        print(f"    negatives: not_found_accuracy={agg['negatives']['not_found_accuracy']}  "
              f"grounding_std={agg['grounding_std']}  judge_errors={agg['judge_errors']}")
        print(f"    tokens: in={in_tok} out={out_tok}")
        return 0 if status == "ok" else 2
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the Phase 10 Part A library eval")
    ap.add_argument("--scope", choices=("core", "full"), default="core")
    ap.add_argument("--limit", type=int, help="cap question count (smoke tests)")
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--budget", type=int, default=TOKEN_BUDGET,
                    help="total token cap (generation + judge)")
    args = ap.parse_args()
    sys.exit(run(args.scope, args.limit, args.top_k, args.budget))
