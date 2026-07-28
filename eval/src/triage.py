"""
eval/src/triage.py — Phase 10 B.5: the improvement loop.

Reviews the poor-result queue (scripts/migrate_part_b.sql poor_results view),
classifies each entry by failure mode, and promotes triaged failures into the
Part A eval library as regression cases (origin='regression'). A fix is
considered closed only when the promoted case passes on a subsequent
scheduled run — check with `closure`.

Usage:
    python eval/src/triage.py list                     # pending queue
    python eval/src/triage.py show <query-id>
    python eval/src/triage.py classify <query-id> --mode retrieval_miss
    python eval/src/triage.py dismiss <query-id>       # not a real failure
    python eval/src/triage.py promote <query-id> [--ground-truth "..."]
    python eval/src/triage.py closure                  # regression pass status

Failure modes (docx B.5): retrieval_miss | corpus_coverage_gap |
generation_error | chunking_artifact | other
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_URL = os.getenv("DATABASE_URL")
FAILURE_MODES = ("retrieval_miss", "corpus_coverage_gap", "generation_error",
                 "chunking_artifact", "other")
REGRESSION_PASS = float(os.getenv("REGRESSION_PASS_THRESHOLD", "0.7"))


def _connect():
    return psycopg.connect(DATABASE_URL)


def cmd_list(_args) -> int:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id::text, created_at::date, reasons, judge_grounding,
                   feedback, left(query_text, 70)
            FROM poor_results WHERE triage_status IS NULL
            ORDER BY created_at DESC LIMIT 100
            """
        ).fetchall()
    if not rows:
        print("[triage] queue is empty")
        return 0
    print(f"[triage] {len(rows)} pending poor results:")
    for r in rows:
        print(f"  {r[0]}  {r[1]}  reasons={r[2]}  grounding={r[3]}  "
              f"feedback={r[4]}\n      {r[5]}")
    return 0


def cmd_show(args) -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT query_text, plain_english, citations, confidence, quality,
                   not_found, judge_grounding, security_downgrade, feedback,
                   triage_status, failure_mode, promoted_question_id::text
            FROM queries WHERE id = %s
            """, (args.id,),
        ).fetchone()
    if not row:
        print("not found")
        return 1
    cols = ("query_text", "plain_english", "citations", "confidence", "quality",
            "not_found", "judge_grounding", "security_downgrade", "feedback",
            "triage_status", "failure_mode", "promoted_question_id")
    print(json.dumps(dict(zip(cols, row)), indent=2, default=str))
    return 0


def cmd_classify(args) -> int:
    if args.mode not in FAILURE_MODES:
        print(f"--mode must be one of {FAILURE_MODES}")
        return 1
    with _connect() as conn:
        n = conn.execute(
            """
            UPDATE queries SET triage_status = 'triaged', failure_mode = %s,
                               triaged_at = NOW()
            WHERE id = %s
            """, (args.mode, args.id),
        ).rowcount
        conn.commit()
    print(f"[triage] {'classified' if n else 'NOT FOUND'}: {args.id} -> {args.mode}")
    return 0 if n else 1


def cmd_dismiss(args) -> int:
    with _connect() as conn:
        n = conn.execute(
            "UPDATE queries SET triage_status = 'dismissed', triaged_at = NOW() "
            "WHERE id = %s", (args.id,),
        ).rowcount
        conn.commit()
    print(f"[triage] {'dismissed' if n else 'NOT FOUND'}: {args.id}")
    return 0 if n else 1


def cmd_promote(args) -> int:
    """Promote a triaged poor result into the library as a regression case."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT query_text, citations, failure_mode FROM queries WHERE id = %s",
            (args.id,),
        ).fetchone()
        if not row:
            print("not found")
            return 1
        query_text, citations, failure_mode = row
        if failure_mode is None and not args.force:
            print("[triage] classify the failure mode first (or --force)")
            return 1
        cites = (json.loads(citations) if isinstance(citations, str)
                 else (citations or []))
        anchor = cites[0] if cites else {}

        qid = conn.execute(
            """
            INSERT INTO eval_questions
                (question, question_type, ground_truth, ground_truth_reference,
                 anchor_cfr_reference, anchor_title, anchor_effective_date, origin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'regression')
            RETURNING id::text
            """,
            (query_text, args.type, args.ground_truth,
             anchor.get("cfr_reference"),
             anchor.get("cfr_reference"), anchor.get("title_number"),
             anchor.get("effective_date")),
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE queries SET triage_status = 'promoted',
                               promoted_question_id = %s, triaged_at = NOW()
            WHERE id = %s
            """, (qid, args.id),
        )
        conn.commit()
    print(f"[triage] promoted {args.id} -> eval_questions {qid} "
          f"(origin=regression, type={args.type})")
    if not args.ground_truth:
        print("[triage] no --ground-truth given: correctness will fall back to "
              "the judge's grounding score on eval runs")
    return 0


def cmd_closure(_args) -> int:
    """Regression-case closure: does each promoted case pass on the latest run?"""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT q.id::text, left(q.question, 60), q.created_at::date,
                   latest.composite, latest.run_id, runs_since.n
            FROM eval_questions q
            LEFT JOIN LATERAL (
                SELECT r.composite, r.run_id FROM eval_results r
                WHERE r.question_id = q.id ORDER BY r.id DESC LIMIT 1
            ) latest ON TRUE
            LEFT JOIN LATERAL (
                SELECT count(*) AS n FROM eval_runs e
                WHERE e.run_at > q.created_at AND e.status = 'ok'
            ) runs_since ON TRUE
            WHERE q.origin = 'regression' AND q.status = 'active'
            ORDER BY q.created_at
            """
        ).fetchall()
    if not rows:
        print("[triage] no promoted regression cases")
        return 0
    closed = overdue = 0
    print(f"[triage] {len(rows)} regression cases (pass = composite >= {REGRESSION_PASS}):")
    for qid, question, created, composite, run_id, runs_since in rows:
        passing = composite is not None and composite >= REGRESSION_PASS
        closed += passing
        state = "CLOSED" if passing else (
            "never evaluated" if composite is None else f"OPEN (composite={composite})")
        if not passing and (runs_since or 0) >= 2:
            state += "  <-- open beyond 2 runs: re-triage"
            overdue += 1
        print(f"  {qid}  {created}  {state}\n      {question}")
    print(f"[triage] closure: {closed}/{len(rows)} closed, {overdue} overdue for re-triage")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 10 B.5 poor-result triage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("show"); p.add_argument("id")
    p = sub.add_parser("classify"); p.add_argument("id")
    p.add_argument("--mode", required=True, choices=FAILURE_MODES)
    p = sub.add_parser("dismiss"); p.add_argument("id")
    p = sub.add_parser("promote"); p.add_argument("id")
    p.add_argument("--ground-truth", default=None)
    p.add_argument("--type", default="regression",
                   help="question_type for the promoted case (default 'regression')")
    p.add_argument("--force", action="store_true",
                   help="promote without a classified failure mode")
    sub.add_parser("closure")
    args = ap.parse_args()
    return {"list": cmd_list, "show": cmd_show, "classify": cmd_classify,
            "dismiss": cmd_dismiss, "promote": cmd_promote,
            "closure": cmd_closure}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
