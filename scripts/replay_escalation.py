"""
scripts/replay_escalation.py — Phase 10 B.1: validate the escalation band
against real traffic before trusting the thresholds.

Replays every persisted query's stored confidence payload through the SAME
band function production uses (src/escalation.escalation_reason) and reports
the escalation rate — the <25% target is validated against actual traffic,
not assumed. No LLM calls; reads queries.confidence only.

Usage:
    python scripts/replay_escalation.py                # current env thresholds
    python scripts/replay_escalation.py --sweep        # margin grid
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import src.escalation as esc  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL")


def load_confidences() -> list[dict]:
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT confidence FROM queries WHERE confidence IS NOT NULL"
        ).fetchall()
    out = []
    for (c,) in rows:
        out.append(json.loads(c) if isinstance(c, str) else c)
    return out


def rate(confs: list[dict]) -> tuple[float, dict]:
    reasons: dict[str, int] = {}
    hits = 0
    for c in confs:
        r = esc.escalation_reason(c)
        if r:
            hits += 1
            reasons[r] = reasons.get(r, 0) + 1
    return (hits / len(confs) if confs else 0.0), reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true",
                    help="sweep ESCALATION_MARGIN over a grid")
    args = ap.parse_args()

    confs = load_confidences()
    if not confs:
        print("[replay] no persisted queries with confidence — nothing to replay")
        return 1
    answered = [c for c in confs if c.get("tier") != "not_found"]
    print(f"[replay] {len(confs)} persisted queries "
          f"({len(answered)} answered, {len(confs) - len(answered)} not_found)")

    if args.sweep:
        print(f"{'margin':>8} {'esc rate':>9}  reasons")
        for margin in (0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15):
            esc.ESCALATION_MARGIN = margin
            r, reasons = rate(confs)
            flag = "  <-- exceeds 25% target" if r >= 0.25 else ""
            print(f"{margin:>8.2f} {r:>8.1%}  {reasons}{flag}")
        return 0

    r, reasons = rate(confs)
    print(f"[replay] escalation rate at current thresholds "
          f"(margin={esc.ESCALATION_MARGIN}, retr>={esc.ESCALATION_RETRIEVAL_HIGH}, "
          f"cov<={esc.ESCALATION_COVERAGE_LOW}): {r:.1%}")
    print(f"[replay] by reason: {reasons}")
    print(f"[replay] target: <25% — {'OK' if r < 0.25 else 'EXCEEDED: raise thresholds'}")
    return 0


if __name__ == "__main__":
    main()
