#!/usr/bin/env python3
"""
scripts/swap_version.py — Phase 9 atomic version swap for the chunks corpus.

Promotes a freshly-staged corpus version to live in a single transaction, so no
query ever sees a missing or half-updated section:

    staged (new)  ->  active
    active (old)  ->  archived

Retrieval filters WHERE status = 'active' (enforced in src/query.py), so the
swap is zero-downtime. Archived chunks are retained by default (they back
temporal "what changed" queries and rollback); pass --delete-archived to drop
them (use for fixing bug-staged data that isn't a meaningful prior version).

Usage:
    # Promote staged version v2026-06-02-refresh for these titles:
    python scripts/swap_version.py --titles 10 14 29 40 49 --version-id v2026-06-02-refresh
    # Same, dropping the superseded (stale) rows instead of archiving:
    python scripts/swap_version.py --titles ... --version-id ... --delete-archived
    # Roll a swap back (reactivate the archived version, re-stage the promoted one):
    python scripts/swap_version.py --rollback --titles ... --version-id v2026-06-02-refresh
    # Inspect without changing anything:
    python scripts/swap_version.py --titles ... --version-id ... --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))


def counts(cur, titles: list[int]) -> dict:
    cur.execute(
        "SELECT status, count(*) FROM chunks WHERE title_number = ANY(%s) GROUP BY status",
        (titles,),
    )
    return dict(cur.fetchall())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", type=int, nargs="+", required=True)
    ap.add_argument("--version-id", required=True, help="version_id of the staged batch to promote")
    ap.add_argument("--delete-archived", action="store_true",
                    help="DELETE superseded rows instead of marking them 'archived'")
    ap.add_argument("--rollback", action="store_true",
                    help="Reverse a prior swap: demote this version to staged, reactivate archived")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = False
    cur = conn.cursor()

    print(f"Titles {args.titles} — status counts before: {counts(cur, args.titles)}")

    if args.rollback:
        # Reverse: the promoted version -> staged; archived rows for these titles -> active.
        cur.execute("UPDATE chunks SET status='staged' WHERE version_id=%s AND status='active'",
                    (args.version_id,))
        demoted = cur.rowcount
        cur.execute("UPDATE chunks SET status='active' "
                    "WHERE title_number = ANY(%s) AND status='archived'", (args.titles,))
        restored = cur.rowcount
        print(f"  rollback: {demoted} demoted active->staged, {restored} restored archived->active")
    else:
        # Forward swap. Verify the staged batch is present first.
        cur.execute("SELECT count(*), count(DISTINCT title_number) FROM chunks "
                    "WHERE version_id=%s AND status='staged'", (args.version_id,))
        staged_n, staged_titles = cur.fetchone()
        if staged_n == 0:
            print(f"  ERROR: no staged chunks with version_id={args.version_id}. Aborting.")
            conn.rollback()
            return 1
        print(f"  staged to promote: {staged_n} chunks across {staged_titles} titles")

        cur.execute("UPDATE chunks SET status='archived' "
                    "WHERE title_number = ANY(%s) AND status='active'", (args.titles,))
        archived = cur.rowcount
        cur.execute("UPDATE chunks SET status='active' WHERE version_id=%s AND status='staged'",
                    (args.version_id,))
        activated = cur.rowcount
        print(f"  swap: {archived} active->archived, {activated} staged->active")

        if args.delete_archived:
            cur.execute("DELETE FROM chunks WHERE title_number = ANY(%s) AND status='archived'",
                        (args.titles,))
            print(f"  deleted {cur.rowcount} archived (superseded) rows")

    if args.dry_run:
        conn.rollback()
        print("  [dry-run] rolled back, no changes committed")
    else:
        conn.commit()
        print("  committed.")

    print(f"Titles {args.titles} — status counts after:  {counts(cur, args.titles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
