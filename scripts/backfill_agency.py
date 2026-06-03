#!/usr/bin/env python3
"""
scripts/backfill_agency.py — populate chunks.agency from the eCFR structure API.

The original agency inference parsed the chapter HEAD with a regex that only
matched an em-dash separator, so titles whose heads use " - " (10, 14, 29, 49)
and titles fetched part-by-part (40, which has no chapter element in per-part
XML) ended up with NULL agency. The structure API exposes the agency cleanly as
each chapter node's `label_description`, so we map part -> agency from there and
backfill. Structure is authoritative, so existing values are overwritten for
consistency.

Usage:
    python scripts/backfill_agency.py            # all titles in the DB
    python scripts/backfill_agency.py --title 40 # one title
    python scripts/backfill_agency.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))

ECFR_API_BASE = os.getenv("ECFR_API_BASE", "https://www.ecfr.gov/api/versioner/v1")


def latest_date(title: int) -> str:
    """Authoritative latest issue date from titles.json (NOT content_versions,
    which is unsorted/capped and yields stale dates → structure 404s)."""
    r = httpx.get(f"{ECFR_API_BASE}/titles.json", timeout=30)
    r.raise_for_status()
    for t in r.json().get("titles", []):
        if t.get("number") == title:
            return t["latest_issue_date"]
    raise ValueError(f"title {title} not found in titles.json")


def part_agency_map(title: int, as_of_date: str) -> dict[str, str]:
    """Walk the structure tree → {part_identifier: agency (chapter label_description)}."""
    r = httpx.get(f"{ECFR_API_BASE}/structure/{as_of_date}/title-{title}.json", timeout=60)
    r.raise_for_status()
    mapping: dict[str, str] = {}

    def walk(node: dict, agency: str | None) -> None:
        if node.get("type") == "chapter":
            agency = (node.get("label_description") or "").strip() or agency
        if node.get("type") == "part":
            ident = node.get("identifier")
            if ident is not None and agency:
                mapping[str(ident)] = agency
        for child in node.get("children") or []:
            walk(child, agency)

    walk(r.json(), None)
    return mapping


def backfill(conn: psycopg.Connection, title: int, dry_run: bool) -> tuple[int, int]:
    as_of = latest_date(title)
    mapping = part_agency_map(title, as_of)
    if not mapping:
        print(f"  title {title}: no part→agency mapping found (as_of {as_of})")
        return 0, 0

    updated = 0
    with conn.cursor() as cur:
        for part, agency in mapping.items():
            cur.execute(
                "UPDATE chunks SET agency = %s "
                "WHERE title_number = %s AND part_number = %s "
                "AND agency IS DISTINCT FROM %s",
                (agency, title, part, agency),
            )
            updated += cur.rowcount
    if dry_run:
        conn.rollback()
    else:
        conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM chunks WHERE title_number = %s AND agency IS NULL", (title,)
        )
        still_null = cur.fetchone()[0]
    print(f"  title {title} (as_of {as_of}): {len(mapping)} parts mapped, "
          f"{updated} rows updated, {still_null} still NULL{'  [dry-run]' if dry_run else ''}")
    return updated, still_null


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", type=int, help="single title; default = all titles in DB")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg.connect(os.getenv("DATABASE_URL"))
    with conn.cursor() as cur:
        if args.title:
            titles = [args.title]
        else:
            cur.execute("SELECT DISTINCT title_number FROM chunks WHERE title_number IS NOT NULL ORDER BY 1")
            titles = [r[0] for r in cur.fetchall()]

    print(f"Backfilling agency for titles: {titles}")
    total = 0
    for t in titles:
        try:
            u, _ = backfill(conn, t, args.dry_run)
            total += u
        except Exception as exc:  # noqa: BLE001
            print(f"  title {t}: ERROR {exc}")
    print(f"Done. {total} rows updated{' (dry-run, rolled back)' if args.dry_run else ''}.")


if __name__ == "__main__":
    sys.exit(main())
