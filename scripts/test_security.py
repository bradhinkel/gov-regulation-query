#!/usr/bin/env python3
"""
scripts/test_security.py — Phase 8.5 adversarial harness.

Runs the 10 adversarial cases in eval/data/adversarial_cases.json against the
security layers and reports pass/fail. Two layers are checked deterministically
and offline:

  check=validate  → backend.security.validate_query must reject (HTTP 400 path)
  check=classify  → src.generate.classify_intent must return False (off-topic)

check=generation cases depend on the full retrieval+generation pipeline (DB +
LLM) and are listed for manual / integration verification, not asserted here.

Usage:
    python scripts/test_security.py              # validate-only (no API key needed)
    python scripts/test_security.py --classify   # also run the live Haiku classifier
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.security import validate_query, QueryValidationError

CASES_PATH = PROJECT_ROOT / "eval" / "data" / "adversarial_cases.json"


def run() -> int:
    parser = argparse.ArgumentParser(description="Phase 8.5 adversarial security harness")
    parser.add_argument(
        "--classify", action="store_true",
        help="Also run live classify_intent checks (requires ANTHROPIC_API_KEY).",
    )
    args = parser.parse_args()

    cases = json.loads(CASES_PATH.read_text())["cases"]
    classify_intent = None
    if args.classify:
        from src.generate import classify_intent  # noqa: lazy — avoids client init otherwise

    passed = failed = skipped = 0
    for c in cases:
        cid, check, query = c["id"], c["check"], c["query"]

        if check == "validate":
            try:
                validate_query(query)
                ok, detail = False, "accepted (expected rejection)"
            except QueryValidationError as exc:
                ok, detail = True, f"rejected: {exc}"
        elif check == "classify":
            if not args.classify:
                print(f"  SKIP  {cid:6} [{check}]  (pass --classify to run live)")
                skipped += 1
                continue
            is_reg = classify_intent(query)
            ok = is_reg is False
            detail = "classified off_topic" if ok else "classified REGULATORY (expected off_topic)"
        else:  # generation
            print(f"  SKIP  {cid:6} [{check}]  needs full pipeline — {c['expected_outcome']}")
            skipped += 1
            continue

        flag = "PASS" if ok else "FAIL"
        print(f"  {flag}  {cid:6} [{check}]  {detail}")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n  {passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
