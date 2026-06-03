"""
src/sync.py — Phase 9.2/9.3 incremental corpus sync (change detection + swap).

The corpus is kept current by applying DELTAS, never rebuilding. The same path
handles a weekly run and a months-long catch-up — the delta is just larger:

  For each title:
    1. watermark = sync_state.last_synced_date (eCFR edition we've reconciled to)
    2. edition   = titles.json latest_issue_date
    3. From the versioner content-versions list, collect sections whose amendment
       date > watermark: `updated` (re-fetch) and `removed` (archive).
    4. If the change set exceeds CHANGE_THRESHOLD of the title, raise an alert and
       skip (likely a bulk regulatory overhaul needing manual review).
    5. Re-fetch + re-embed only the changed sections, insert as status='staged'.
    6. Atomic per-section swap: archive superseded active chunks, activate staged;
       archive removed sections. Retains archived versions for temporal queries.
    7. Advance the watermark; log the run.

Only a handful of rows move per run, so there's no HNSW index churn (cf. the
one-time full bootstrap, which required drop/rebuild).

Usage:
    python src/sync.py                 # sync all titles in sync_state
    python src/sync.py --titles 14 40  # specific titles
    python src/sync.py --dry-run       # report the delta, change nothing
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv
from lxml import etree
from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

from src.parsers.xml_parser import (
    ECFRXMLParser, ECFR_API_BASE, _get_latest_date, _part_agency_map, _get_with_retry,
)
from src.ingest import embed_chunks, insert_chunks

DATABASE_URL = os.getenv("DATABASE_URL")
CHANGE_THRESHOLD = float(os.getenv("SYNC_CHANGE_THRESHOLD", "0.20"))
console = Console()


def _changed_sections(title: int, since_date: str) -> tuple[dict, dict]:
    """
    Return ({(part, section): entry} updated, {(part, section): entry} removed)
    for sections issued after `since_date`.

    IMPORTANT: the unfiltered /versions endpoint is capped (~1000 entries) and
    returns an OLD subset, so it silently hides recent amendments. We must pass
    the issue_date[gte] filter to get the actual recent change set.
    """
    url = f"{ECFR_API_BASE}/versions/title-{title}.json"
    data = json.loads(_get_with_retry(url, params={"issue_date[gte]": since_date}))
    updated: dict = {}
    removed: dict = {}
    for e in data.get("content_versions", []):
        if e.get("type") != "section":
            continue
        # Strictly after the watermark — the edition issued *on* since_date is
        # already in the corpus.
        if (e.get("issue_date") or e.get("date") or "") <= since_date:
            continue
        key = (e.get("part"), e.get("identifier"))
        if e.get("removed"):
            removed[key] = e
        else:
            updated[key] = e
    # A section reappearing after removal counts as updated, not removed.
    for k in list(removed):
        if k in updated:
            del removed[k]
    return updated, removed


def _fetch_section_chunks(parser, title, edition, part, section_id, agency_map):
    """Fetch one section's current XML, parse it, and stamp known part/agency."""
    content = _get_with_retry(
        f"{ECFR_API_BASE}/full/{edition}/title-{title}.xml", params={"section": section_id}
    )
    root = etree.fromstring(content)
    chunks = [c for c in parser._parse_roots([root], title, edition, agency_map)
              if c.section_number == section_id]
    # Per-section XML omits the PART ancestor, so set part/agency from the manifest.
    for c in chunks:
        c.part_number = part
        if not c.agency:
            c.agency = agency_map.get(part)
    return chunks


def _cfr_ref(title: int, section_id: str) -> str:
    return f"{title} CFR § {section_id}"


def sync_title(conn: psycopg.Connection, parser, title: int, dry_run: bool) -> dict:
    row = conn.execute(
        "SELECT last_synced_date::text FROM sync_state WHERE title_number=%s", (title,)
    ).fetchone()
    if row:
        watermark = row[0]
    else:
        r = conn.execute(
            "SELECT max(effective_date)::text FROM chunks WHERE title_number=%s AND status='active'",
            (title,),
        ).fetchone()
        watermark = (r and r[0]) or "1900-01-01"

    edition = _get_latest_date(title)
    updated, removed = _changed_sections(title, watermark)

    active_sections = conn.execute(
        "SELECT count(DISTINCT cfr_reference) FROM chunks WHERE title_number=%s AND status='active'",
        (title,),
    ).fetchone()[0]
    change_count = len(updated) + len(removed)

    base = {"title": title, "watermark": watermark, "edition": edition,
            "updated": len(updated), "removed": len(removed)}

    if active_sections and change_count / active_sections > CHANGE_THRESHOLD:
        return {**base, "status": "alert",
                "reason": f"{change_count}/{active_sections} sections changed "
                          f"(> {CHANGE_THRESHOLD:.0%}); manual review"}

    if change_count == 0:
        if not dry_run:
            _set_watermark(conn, title, edition)
        return {**base, "status": "up_to_date"}

    if dry_run:
        return {**base, "status": "dry_run"}

    # ── Stage changed sections ────────────────────────────────────────────────
    run_tag = f"sync-{int(time.time())}-t{title}"
    agency_map = _part_agency_map(title, edition)
    staged = 0
    for (part, sec) in updated:
        try:
            chunks = _fetch_section_chunks(parser, title, edition, part, sec, agency_map)
        except Exception as exc:  # noqa: BLE001 — skip a stubborn section, keep going
            console.print(f"  [yellow]title {title} section {sec} fetch failed: {exc}[/yellow]")
            continue
        if not chunks:
            continue
        embeddings = embed_chunks([c.chunk_text for c in chunks])
        insert_chunks(conn, chunks, embeddings, version_id=run_tag, status="staged")
        conn.commit()
        staged += len(chunks)

    # ── Atomic swap (one transaction) ─────────────────────────────────────────
    updated_refs = [_cfr_ref(title, sec) for (_p, sec) in updated]
    removed_refs = [_cfr_ref(title, sec) for (_p, sec) in removed]
    with conn.cursor() as cur:
        if updated_refs:
            cur.execute(
                "UPDATE chunks SET status='archived' "
                "WHERE title_number=%s AND status='active' AND cfr_reference = ANY(%s)",
                (title, updated_refs),
            )
            cur.execute(
                "UPDATE chunks SET status='active' WHERE version_id=%s AND status='staged'",
                (run_tag,),
            )
        if removed_refs:
            cur.execute(
                "UPDATE chunks SET status='archived' "
                "WHERE title_number=%s AND status='active' AND cfr_reference = ANY(%s)",
                (title, removed_refs),
            )
    conn.commit()
    _set_watermark(conn, title, edition)
    return {**base, "status": "synced", "staged": staged}


def _set_watermark(conn, title, edition):
    conn.execute(
        "INSERT INTO sync_state (title_number, last_synced_date, updated_at) "
        "VALUES (%s, %s, now()) "
        "ON CONFLICT (title_number) DO UPDATE SET last_synced_date=EXCLUDED.last_synced_date, updated_at=now()",
        (title, edition),
    )
    conn.commit()


def run_sync(titles: list[int] | None, dry_run: bool) -> None:
    conn = psycopg.connect(DATABASE_URL)
    if not titles:
        titles = [r[0] for r in conn.execute(
            "SELECT title_number FROM sync_state ORDER BY title_number").fetchall()]
    parser = ECFRXMLParser()

    console.print(f"[bold]Incremental sync[/bold] — titles {titles}  dry_run={dry_run}")
    results = []
    for t in titles:
        try:
            res = sync_title(conn, parser, t, dry_run)
        except Exception as exc:  # noqa: BLE001
            res = {"title": t, "status": "error", "reason": str(exc)}
        results.append(res)
        console.print(f"  title {res['title']}: [cyan]{res['status']}[/cyan] "
                      f"updated={res.get('updated', 0)} removed={res.get('removed', 0)} "
                      f"staged={res.get('staged', 0)} edition={res.get('edition', '?')}"
                      + (f"  ({res['reason']})" if res.get('reason') else ""))

    totals = {
        "sections_updated": sum(r.get("updated", 0) for r in results if r["status"] == "synced"),
        "sections_removed": sum(r.get("removed", 0) for r in results if r["status"] == "synced"),
        "titles_changed": sum(1 for r in results if r["status"] == "synced"),
    }
    overall = ("error" if any(r["status"] == "error" for r in results)
               else "alert" if any(r["status"] == "alert" for r in results)
               else "dry_run" if dry_run else "ok")
    if not dry_run:
        conn.execute(
            "INSERT INTO sync_runs (titles, titles_changed, sections_updated, sections_removed, status, manifest) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (titles, totals["titles_changed"], totals["sections_updated"],
             totals["sections_removed"], overall, json.dumps(results)),
        )
        conn.commit()
    console.print(f"[bold]Done[/bold] — {overall}: {totals}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Incremental eCFR corpus sync")
    ap.add_argument("--titles", type=int, nargs="+", help="titles to sync (default: all in sync_state)")
    ap.add_argument("--dry-run", action="store_true", help="report delta, change nothing")
    args = ap.parse_args()
    run_sync(args.titles, args.dry_run)
