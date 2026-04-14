"""
eval/src/generate_dataset.py — Generate evaluation dataset from indexed regulations.

Samples representative chunks across CFR titles and uses Claude to generate
realistic regulatory questions with ground-truth answers and CFR references.

Usage:
    python eval/src/generate_dataset.py --questions-per-title 5
    python eval/src/generate_dataset.py --title 7 --questions-per-title 10
    python eval/src/generate_dataset.py --output eval/data/eval_dataset.json
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

import anthropic
import psycopg
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag",
)
GENERATOR_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OUTPUT = str(PROJECT_ROOT / "eval" / "data" / "eval_dataset.json")

_anthropic = anthropic.Anthropic()


def sample_chunks(
    title_number: int | None = None,
    n_per_title: int = 5,
    source_system: str = "federal_regulations",
) -> list[dict]:
    """Sample representative regulation chunks from the DB."""
    conn = psycopg.connect(DATABASE_URL)
    try:
        if title_number:
            rows = conn.execute(
                """
                SELECT id::text, cfr_reference, section_heading, chunk_text, title_number, part_number
                FROM chunks
                WHERE source_system = %s AND status = 'active' AND title_number = %s
                ORDER BY RANDOM()
                LIMIT %s
                """,
                (source_system, title_number, n_per_title),
            ).fetchall()
        else:
            # Sample across all titles
            titles = conn.execute(
                "SELECT DISTINCT title_number FROM chunks WHERE source_system = %s AND status = 'active' AND title_number IS NOT NULL ORDER BY title_number",
                (source_system,),
            ).fetchall()
            rows = []
            for (tn,) in titles:
                title_rows = conn.execute(
                    """
                    SELECT id::text, cfr_reference, section_heading, chunk_text, title_number, part_number
                    FROM chunks
                    WHERE source_system = %s AND status = 'active' AND title_number = %s
                    ORDER BY RANDOM()
                    LIMIT %s
                    """,
                    (source_system, tn, n_per_title),
                ).fetchall()
                rows.extend(title_rows)
    finally:
        conn.close()

    return [
        {
            "chunk_id": r[0],
            "cfr_reference": r[1],
            "section_heading": r[2],
            "chunk_text": r[3],
            "title_number": r[4],
            "part_number": r[5],
        }
        for r in rows
    ]


_QA_SYSTEM = """\
You are generating evaluation questions for a federal regulation RAG system.
Given a regulation section, produce a realistic question that a compliance officer,
attorney, or regulated entity might ask — and a concise ground-truth answer.
The question should be answerable from the provided text.
Respond with ONLY a JSON object."""

_QA_PROMPT = """\
Regulation section:
{cfr_reference} — {section_heading}

{chunk_text}

Generate ONE question-answer pair. The question must be answerable from the section above.
Respond with ONLY:
{{
  "question": "...",
  "ground_truth": "One to three sentence answer grounded in the regulation text.",
  "ground_truth_reference": "{cfr_reference}"
}}"""


def generate_qa_pair(chunk: dict) -> dict | None:
    """Use Claude to generate a question-answer pair from a chunk."""
    prompt = _QA_PROMPT.format(
        cfr_reference=chunk["cfr_reference"] or "Unknown",
        section_heading=chunk["section_heading"] or "",
        chunk_text=chunk["chunk_text"][:1500],
    )
    try:
        response = _anthropic.messages.create(
            model=GENERATOR_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            system=_QA_SYSTEM,
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return {
            "question": data["question"],
            "ground_truth": data["ground_truth"],
            "ground_truth_reference": data.get("ground_truth_reference", chunk["cfr_reference"] or ""),
            "source_chunk_id": chunk["chunk_id"],
            "cfr_reference": chunk["cfr_reference"],
            "title_number": chunk["title_number"],
        }
    except Exception as exc:
        print(f"  [warn] Failed to generate QA for {chunk['cfr_reference']}: {exc}")
        return None


def generate_dataset(
    title_number: int | None,
    questions_per_title: int,
    output_path: str,
    source_system: str = "federal_regulations",
):
    print(f"[gen] Sampling chunks from DB...")
    chunks = sample_chunks(
        title_number=title_number,
        n_per_title=questions_per_title,
        source_system=source_system,
    )
    print(f"[gen] Sampled {len(chunks)} chunks")

    questions = []
    for i, chunk in enumerate(chunks):
        print(f"  [{i+1}/{len(chunks)}] {chunk['cfr_reference']}...")
        qa = generate_qa_pair(chunk)
        if qa:
            qa["id"] = f"q{i+1:03d}"
            questions.append(qa)

    dataset = {
        "version": "1.0",
        "source_system": source_system,
        "num_questions": len(questions),
        "questions": questions,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"\n[gen] Done. {len(questions)} questions → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate regulation eval dataset")
    parser.add_argument("--title", type=int, help="Limit to a specific CFR title number")
    parser.add_argument("--questions-per-title", type=int, default=5)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--source-system", default="federal_regulations")
    args = parser.parse_args()

    generate_dataset(
        title_number=args.title,
        questions_per_title=args.questions_per_title,
        output_path=args.output,
        source_system=args.source_system,
    )
