"""
src/ingest.py — Ingestion pipeline for federal regulations via eCFR API.

Fetches regulation XML from eCFR, chunks at § section boundaries,
embeds with text-embedding-3-small, and stores in PostgreSQL + pgvector.

Each ingest run is tagged with a version_id (ISO date). Chunks are written
as 'active' by default. Phase 8 will add atomic-swap promotion logic.

Usage:
    python src/ingest.py --title 7         # ingest Title 7 (Agriculture)
    python src/ingest.py --title 21        # ingest Title 21 (Food & Drugs)
    python src/ingest.py --titles 7 21 42  # ingest multiple titles
    python src/ingest.py --dry-run --title 7  # parse only, no DB writes
    python src/ingest.py --reset --title 7    # delete existing, then re-ingest
"""

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.base import ChunkWithMetadata
from src.parsers.xml_parser import ECFRXMLParser

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_BATCH_SIZE = 100
SOURCE_SYSTEM = os.getenv("SOURCE_SYSTEM", "federal_regulations")

console = Console()
openai_client = OpenAI()


def embed_chunks(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns list of 1536-dim vectors."""
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def already_ingested(conn: psycopg.Connection, source_id: str, source_system: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE source_id = %s AND source_system = %s AND status = 'active'",
        (source_id, source_system),
    ).fetchone()
    return row[0] > 0


def _clean(s: str | None) -> str | None:
    """Strip NUL bytes that PostgreSQL rejects in text fields."""
    return s.replace("\x00", "") if s is not None else None


def insert_chunks(
    conn: psycopg.Connection,
    chunks: list[ChunkWithMetadata],
    embeddings: list[list[float]],
    version_id: str,
):
    """Bulk insert regulatory chunks with their embeddings."""
    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        rows.append((
            _clean(chunk.source_system),
            _clean(chunk.corpus_type),
            _clean(chunk.source_id),
            chunk.title_number,
            _clean(chunk.part_number),
            _clean(chunk.subpart),
            _clean(chunk.section_number),
            _clean(chunk.section_heading),
            _clean(chunk.agency),
            _clean(chunk.cfr_reference),
            chunk.effective_date,
            _clean(chunk.location_reference),
            chunk.chunk_index,
            _clean(chunk.chunk_text),
            embedding,
            version_id,
        ))

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks (
                source_system, corpus_type, source_id,
                title_number, part_number, subpart,
                section_number, section_heading, agency,
                cfr_reference, effective_date,
                location_reference, chunk_index,
                chunk_text, embedding, version_id
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s::vector, %s
            )
            """,
            rows,
        )


def ingest_title(
    title_number: int,
    conn: psycopg.Connection | None,
    dry_run: bool,
    parser: ECFRXMLParser,
    version_id: str,
) -> dict:
    """Ingest a single CFR title."""
    source_id = parser.source_id_for(title_number)
    source_system = parser.source_system

    if not dry_run and conn and already_ingested(conn, source_id, source_system):
        return {
            "title": title_number,
            "status": "skipped",
            "reason": "already ingested",
            "source_id": source_id,
        }

    t0 = time.time()
    all_chunks: list[ChunkWithMetadata] = []

    try:
        for chunk in parser.parse(title_number):
            all_chunks.append(chunk)
    except Exception as exc:
        return {"title": title_number, "status": "error", "error": str(exc)}

    if not all_chunks:
        return {"title": title_number, "status": "skipped", "reason": "no chunks extracted"}

    if dry_run:
        elapsed = time.time() - t0
        return {
            "title": title_number,
            "status": "dry_run",
            "chunks": len(all_chunks),
            "source_id": source_id,
            "parse_s": round(elapsed, 1),
        }

    # Embed in batches
    embed_t0 = time.time()
    all_embeddings: list[list[float]] = []
    try:
        for i in range(0, len(all_chunks), EMBEDDING_BATCH_SIZE):
            batch = all_chunks[i: i + EMBEDDING_BATCH_SIZE]
            texts = [c.chunk_text for c in batch]
            embeddings = embed_chunks(texts)
            all_embeddings.extend(embeddings)
    except Exception as exc:
        return {"title": title_number, "status": "error", "error": f"embedding failed: {exc}"}
    embed_s = time.time() - embed_t0

    insert_chunks(conn, all_chunks, all_embeddings, version_id)
    conn.commit()

    elapsed = time.time() - t0
    return {
        "title": title_number,
        "status": "ok",
        "chunks": len(all_chunks),
        "source_id": source_id,
        "elapsed_s": round(elapsed, 1),
        "embed_s": round(embed_s, 1),
    }


def reset_title(conn: psycopg.Connection, title_number: int, source_system: str):
    conn.execute(
        "DELETE FROM chunks WHERE title_number = %s AND source_system = %s",
        (title_number, source_system),
    )
    conn.commit()
    console.print(f"[yellow]Deleted existing chunks for Title {title_number} / {source_system}[/yellow]")


def run_ingestion(
    titles: list[int],
    dry_run: bool,
    reset: bool,
    source_system: str = "federal_regulations",
):
    version_id = date.today().isoformat()
    parser = ECFRXMLParser(source_system=source_system)

    console.print(f"[bold]Government Regulation RAG — Ingestion Pipeline[/bold]")
    console.print(f"Source:        eCFR API (live)")
    console.print(f"Source system: {source_system}")
    console.print(f"Version ID:    {version_id}")
    console.print(f"Titles:        {titles}")
    console.print(f"Dry run:       {dry_run}")
    console.print()

    if dry_run:
        conn = None
    else:
        conn = psycopg.connect(DATABASE_URL, autocommit=False)
        if reset:
            for t in titles:
                reset_title(conn, t, source_system)

    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Ingesting...", total=len(titles))
        for title_number in titles:
            progress.update(task, description=f"[cyan]Title {title_number}[/cyan]")
            result = ingest_title(title_number, conn, dry_run=dry_run, parser=parser, version_id=version_id)
            results.append(result)
            progress.advance(task)

    if conn:
        conn.close()

    # Summary table
    table = Table(title="Ingestion Summary", show_lines=True)
    table.add_column("Title", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Chunks", justify="right")
    table.add_column("Time (s)", justify="right")
    table.add_column("Notes")

    ok = skipped = errors = total_chunks = 0
    for r in results:
        status = r["status"]
        chunks = str(r.get("chunks", ""))
        elapsed = str(r.get("elapsed_s", r.get("parse_s", "")))
        notes = r.get("reason", r.get("error", ""))
        color = {"ok": "green", "dry_run": "blue", "skipped": "yellow", "error": "red"}.get(status, "white")
        table.add_row(
            f"Title {r['title']}",
            f"[{color}]{status}[/{color}]",
            chunks, elapsed, notes,
        )
        if status == "ok":
            ok += 1
            total_chunks += r.get("chunks", 0)
        elif status == "skipped":
            skipped += 1
        elif status == "error":
            errors += 1
        elif status == "dry_run":
            total_chunks += r.get("chunks", 0)

    console.print(table)
    console.print(
        f"\n[bold]Ingested:[/bold] {ok} titles | [bold]Chunks:[/bold] {total_chunks} | "
        f"[bold]Skipped:[/bold] {skipped} | [bold]Errors:[/bold] {errors}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest federal regulations from eCFR API")
    parser.add_argument("--title", type=int, help="Ingest a single CFR title number (e.g. 7)")
    parser.add_argument("--titles", type=int, nargs="+", help="Ingest multiple CFR titles (e.g. 7 21 42)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; no DB writes or embeddings")
    parser.add_argument("--reset", action="store_true", help="Delete existing chunks before re-ingesting")
    parser.add_argument("--source-system", default="federal_regulations", help="source_system tag (default: federal_regulations)")
    args = parser.parse_args()

    if args.title:
        title_list = [args.title]
    elif args.titles:
        title_list = args.titles
    else:
        # Default starter corpus
        title_list = [7, 21, 42]
        console.print("[yellow]No --title specified. Using default starter corpus: Titles 7, 21, 42[/yellow]")

    run_ingestion(
        titles=title_list,
        dry_run=args.dry_run,
        reset=args.reset,
        source_system=args.source_system,
    )
