"""
eval/src/library.py — Phase 10 Part A: the self-maintaining evaluation library.

DB-backed (eval_questions), stratified, and ANCHORED: every generated question
records the CFR section + effective date its ground truth was written against,
so the weekly sync can maintain it:

  seed     Build/extend the library to per-(title × stratum) quotas.
  refresh  Post-sync maintenance: retire questions on removed sections,
           regenerate ground truth where the anchor section changed (the
           question leaves the stable core), top strata back up to quota.
  status   Print stratum coverage, core size, and freshness.

Strata: definition, numeric_standard, procedure, penalty, enumerated_list
(the known Phase 9.7 weak spot), adversarial (the variance source Phase 9.1
lacked), and negative (out-of-corpus questions that must yield not_found).

Usage:
    python eval/src/library.py seed [--titles 7 21] [--scale 1.0] [--dry-run]
    python eval/src/library.py refresh [--dry-run]
    python eval/src/library.py status
"""

import argparse
import json
import os
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
# Question generation is cheap authoring work — Haiku is fine here. Judging is
# not (Phase 9.1); the judge lives in src/judge.py and defaults to Sonnet.
GENERATOR_MODEL = os.getenv("EVAL_GENERATOR_MODEL", "claude-haiku-4-5-20251001")
SECTION_TEXT_CAP = 6000

_client = anthropic.Anthropic()

# ── Strata ──────────────────────────────────────────────────────────────────
# Sections are chunked (~1.5K chars/chunk), so candidate selection groups by
# cfr_reference and the predicate (`sql`) is a HAVING clause over the whole
# section's chunks — aggregates (bool_or / sum), not row predicates.
STRATA: dict[str, dict] = {
    "definition": {
        "quota": 3,
        "sql": r"bool_or(section_heading ~* '\mdefinitions?\M|meaning of')",
        "instruction": "Ask what a specific term defined in this section means.",
    },
    "numeric_standard": {
        "quota": 3,
        "sql": r"bool_or(chunk_text ~* '\m\d+(\.\d+)?\s*(percent|ppm|parts per million|milligrams|mg|micrograms|days|hours|feet|pounds|inches|gallons|decibels)\M')",
        "instruction": "Ask about a specific numeric limit, threshold, quantity, or "
                       "deadline in this section. The ground truth must state the number.",
    },
    "procedure": {
        "quota": 3,
        "sql": r"bool_or(section_heading ~* 'procedur|application|filing|submission|request|petition|notification')",
        "instruction": "Ask how a regulated party complies with, applies for, or files "
                       "something under this section.",
    },
    "penalty": {
        "quota": 2,
        "sql": r"bool_or(section_heading ~* 'penalt|violation|enforcement|sanction|prohibit') "
               r"OR bool_or(chunk_text ~* 'civil penalty|criminal penalty')",
        "instruction": "Ask about the consequences, penalties, or enforcement actions "
                       "for a violation covered by this section.",
    },
    "enumerated_list": {
        "quota": 3,
        "sql": r"sum(regexp_count(chunk_text, '\([a-z0-9]{1,3}\)')) >= 10 "
               r"AND sum(length(chunk_text)) > 2000",
        "instruction": "Ask a question whose complete answer requires several items from "
                       "this section's enumerated list (e.g. 'which substances/activities "
                       "are allowed/required'). The ground truth should reflect the "
                       "breadth of the list, not a single item.",
    },
    "adversarial": {
        "quota": 4,
        "sql": r"sum(length(chunk_text)) > 2500",
        "instruction": "Ask a HARD question: it must hinge on an exception, condition, or "
                       "cross-reference inside this section. Phrase it the way a layperson "
                       "would, deliberately avoiding the section's distinctive terminology, "
                       "so simple keyword matching will not find the answer.",
    },
}

NEGATIVE_QUOTA = 16  # global, not per-title
# Regulatory areas in CFR titles the corpus does NOT include (corpus:
# 7, 10, 14, 21, 29, 40, 42, 49). Questions here must yield not_found.
NEGATIVE_TOPICS = [
    ("immigration and visa petitions (8 CFR)", 8),
    ("national banks and lending limits (12 CFR)", 12),
    ("export administration and controlled technology (15 CFR)", 15),
    ("securities registration and broker-dealers (17 CFR)", 17),
    ("HUD public housing assistance (24 CFR)", 24),
    ("federal income tax withholding (26 CFR)", 26),
    ("alcohol and tobacco trade practices (27 CFR)", 27),
    ("patent and trademark examination (37 CFR)", 37),
]

_GEN_SYSTEM = """\
You are generating evaluation questions for a federal regulation RAG system.
Given a regulation section, produce a realistic question that a compliance
officer, attorney, or regulated entity might ask — and a concise ground-truth
answer, both strictly grounded in the provided text.
Respond with ONLY a JSON object."""

_GEN_PROMPT = """\
Regulation section:
{cfr_reference} — {section_heading}

{section_text}

Task: {instruction}
The question must be answerable from the section text above, and it must be
SELF-CONTAINED: a user asks it cold, so never write "this section", "this
regulation", or "under this part" — name the subject matter (program, product,
activity, agency) so the question stands alone.

Respond with ONLY:
{{
  "question": "...",
  "ground_truth": "One to three sentence answer grounded in the section text.",
  "ground_truth_reference": "{cfr_reference}"
}}"""

_NEGATIVE_PROMPT = """\
Generate ONE plausible, specific compliance question about: {topic}.
It must sound like a real question to a federal-regulation assistant, but its
answer lives OUTSIDE these CFR titles: 7 (Agriculture), 10 (Energy),
14 (Aeronautics), 21 (Food and Drugs), 29 (Labor), 40 (Environment),
42 (Public Health), 49 (Transportation).

Respond with ONLY:
{{"question": "..."}}"""

_REFRESH_SYSTEM = """\
You maintain ground-truth answers for a regulation eval set after the underlying
section text was amended. Respond with ONLY a JSON object."""

_REFRESH_PROMPT = """\
Current text of {cfr_reference}:
{section_text}

Existing eval question:
{question}

If the question is still answerable from the current text, write a fresh one to
three sentence ground-truth answer from the CURRENT text. If the current text no
longer answers it, set answerable to false.

Respond with ONLY:
{{"answerable": true/false, "ground_truth": "... or null"}}"""


def _llm_json(system: str, prompt: str, max_tokens: int = 512) -> dict | None:
    try:
        r = _client.messages.create(
            model=GENERATOR_MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (r.content[0].text if r.content else "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip().rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — a failed generation is skipped, not fatal
        print(f"    [warn] generation failed: {exc}")
        return None


def _section_text(conn, cfr_reference: str) -> tuple[str, str, object]:
    """Full active text of a section (chunks concatenated), heading, max effective_date."""
    rows = conn.execute(
        "SELECT chunk_text, section_heading, effective_date FROM chunks "
        "WHERE cfr_reference = %s AND status = 'active' ORDER BY chunk_index",
        (cfr_reference,),
    ).fetchall()
    text = "\n".join(r[0] for r in rows)[:SECTION_TEXT_CAP]
    heading = next((r[1] for r in rows if r[1]), "")
    eff = max((r[2] for r in rows if r[2]), default=None)
    return text, heading, eff


def _active_counts(conn) -> dict[tuple, int]:
    """{(title, stratum): active question count}; negatives keyed (None, 'negative')."""
    rows = conn.execute(
        "SELECT anchor_title, question_type, count(*) FROM eval_questions "
        "WHERE status = 'active' GROUP BY 1, 2"
    ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


def _candidate_sections(conn, title: int, stratum_sql: str, limit: int) -> list[str]:
    """Random candidate sections for a stratum, excluding already-anchored ones."""
    rows = conn.execute(
        f"""
        SELECT cfr_reference FROM (
            SELECT cfr_reference FROM chunks
            WHERE status = 'active' AND title_number = %s AND cfr_reference IS NOT NULL
              AND cfr_reference NOT IN (
                  SELECT anchor_cfr_reference FROM eval_questions
                  WHERE status = 'active' AND anchor_cfr_reference IS NOT NULL)
            GROUP BY cfr_reference
            HAVING ({stratum_sql})
        ) candidates
        ORDER BY RANDOM() LIMIT %s
        """,
        (title, limit),
    ).fetchall()
    return [r[0] for r in rows]


def _insert_question(conn, q: dict, dry_run: bool):
    if dry_run:
        print(f"    [dry-run] would insert {q['question_type']}: {q['question'][:80]}")
        return
    conn.execute(
        """
        INSERT INTO eval_questions
            (question, question_type, ground_truth, ground_truth_reference,
             anchor_cfr_reference, anchor_title, anchor_effective_date, origin)
        VALUES (%(question)s, %(question_type)s, %(ground_truth)s,
                %(ground_truth_reference)s, %(anchor_cfr_reference)s,
                %(anchor_title)s, %(anchor_effective_date)s, %(origin)s)
        """,
        q,
    )
    conn.commit()


def _fill_stratum(conn, title: int, stratum: str, needed: int, dry_run: bool) -> int:
    """Generate up to `needed` questions for (title, stratum). Returns count added."""
    spec = STRATA[stratum]
    candidates = _candidate_sections(conn, title, spec["sql"], needed * 3)
    added = 0
    for ref in candidates:
        if added >= needed:
            break
        text, heading, eff = _section_text(conn, ref)
        if len(text) < 300:  # too thin to author a grounded question
            continue
        data = _llm_json(_GEN_SYSTEM, _GEN_PROMPT.format(
            cfr_reference=ref, section_heading=heading or "",
            section_text=text, instruction=spec["instruction"]))
        if not data or not data.get("question") or not data.get("ground_truth"):
            continue
        _insert_question(conn, {
            "question": data["question"],
            "question_type": stratum,
            "ground_truth": data["ground_truth"],
            "ground_truth_reference": data.get("ground_truth_reference") or ref,
            "anchor_cfr_reference": ref,
            "anchor_title": title,
            "anchor_effective_date": eff,
            "origin": "generated",
        }, dry_run)
        added += 1
        print(f"    + {stratum} [{ref}] {data['question'][:70]}")
    return added


def _fill_negatives(conn, needed: int, dry_run: bool) -> int:
    added = 0
    for i in range(needed):
        topic, _title = NEGATIVE_TOPICS[i % len(NEGATIVE_TOPICS)]
        data = _llm_json(_GEN_SYSTEM, _NEGATIVE_PROMPT.format(topic=topic), max_tokens=256)
        if not data or not data.get("question"):
            continue
        _insert_question(conn, {
            "question": data["question"],
            "question_type": "negative",
            "ground_truth": None,
            "ground_truth_reference": None,
            "anchor_cfr_reference": None,
            "anchor_title": None,
            "anchor_effective_date": None,
            "origin": "generated",
        }, dry_run)
        added += 1
        print(f"    + negative: {data['question'][:70]}")
    return added


def _corpus_titles(conn) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT title_number FROM chunks "
        "WHERE status='active' AND title_number IS NOT NULL ORDER BY 1").fetchall()]


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_seed(titles: list[int] | None, scale: float, dry_run: bool):
    conn = psycopg.connect(DATABASE_URL)
    try:
        titles = titles or _corpus_titles(conn)
        counts = _active_counts(conn)
        total = 0
        for title in titles:
            print(f"[seed] Title {title}")
            for stratum, spec in STRATA.items():
                quota = max(1, round(spec["quota"] * scale))
                have = counts.get((title, stratum), 0)
                if have < quota:
                    total += _fill_stratum(conn, title, stratum, quota - have, dry_run)
        neg_quota = max(1, round(NEGATIVE_QUOTA * scale))
        neg_have = counts.get((None, "negative"), 0)
        if neg_have < neg_quota:
            print("[seed] Negatives (out-of-corpus)")
            total += _fill_negatives(conn, neg_quota - neg_have, dry_run)
        print(f"[seed] Done — {total} questions added")
    finally:
        conn.close()


def cmd_refresh(dry_run: bool, top_up: bool = True):
    """
    Post-sync maintenance (Phase 10 A.4). Anchored on the same signal the sync
    itself uses: the active chunks' effective_date per section.
    """
    conn = psycopg.connect(DATABASE_URL)
    try:
        # 1. Retire questions whose anchor section no longer exists (active).
        removed = conn.execute(
            """
            SELECT q.id, q.anchor_cfr_reference FROM eval_questions q
            WHERE q.status = 'active' AND q.anchor_cfr_reference IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM chunks c
                              WHERE c.cfr_reference = q.anchor_cfr_reference
                                AND c.status = 'active')
            """
        ).fetchall()
        for qid, ref in removed:
            print(f"  retire (section removed): {ref}")
            if not dry_run:
                conn.execute(
                    "UPDATE eval_questions SET status='retired', "
                    "retired_reason='section_removed', updated_at=now() WHERE id=%s",
                    (qid,),
                )
        if not dry_run:
            conn.commit()

        # 2. Re-reference questions whose anchor section changed since generation.
        #    The question text survives; the ground truth is rewritten from the
        #    current text; times_refreshed += 1 removes it from the stable core.
        changed = conn.execute(
            """
            SELECT q.id, q.question, q.anchor_cfr_reference,
                   q.anchor_effective_date, max(c.effective_date)
            FROM eval_questions q
            JOIN chunks c ON c.cfr_reference = q.anchor_cfr_reference
                         AND c.status = 'active'
            WHERE q.status = 'active' AND q.anchor_cfr_reference IS NOT NULL
            GROUP BY q.id, q.question, q.anchor_cfr_reference, q.anchor_effective_date
            HAVING q.anchor_effective_date IS NULL
                OR max(c.effective_date) > q.anchor_effective_date
            """
        ).fetchall()
        refreshed = retired = 0
        for qid, question, ref, _old_eff, new_eff in changed:
            if dry_run:
                print(f"  [dry-run] would re-reference: {ref}")
                refreshed += 1
                continue
            text, _heading, eff = _section_text(conn, ref)
            data = _llm_json(_REFRESH_SYSTEM, _REFRESH_PROMPT.format(
                cfr_reference=ref, section_text=text, question=question))
            if data and data.get("answerable") and data.get("ground_truth"):
                conn.execute(
                    "UPDATE eval_questions SET ground_truth=%s, anchor_effective_date=%s, "
                    "times_refreshed=times_refreshed+1, updated_at=now() WHERE id=%s",
                    (data["ground_truth"], eff or new_eff, qid),
                )
                refreshed += 1
                print(f"  re-referenced: {ref}")
            else:
                conn.execute(
                    "UPDATE eval_questions SET status='retired', "
                    "retired_reason='question_obsolete_after_amendment', updated_at=now() "
                    "WHERE id=%s",
                    (qid,),
                )
                retired += 1
                print(f"  retire (no longer answerable): {ref}")
            conn.commit()

        print(f"[refresh] removed-section retirements: {len(removed)}, "
              f"re-referenced: {refreshed}, obsolete: {retired}")

        # 3. Top strata back up to quota (replaces retired questions).
        if top_up and not dry_run:
            cmd_seed(None, scale=1.0, dry_run=False)
    finally:
        conn.close()


def cmd_status():
    conn = psycopg.connect(DATABASE_URL)
    try:
        rows = conn.execute(
            """
            SELECT coalesce(anchor_title, 0), question_type,
                   count(*) FILTER (WHERE status='active'),
                   count(*) FILTER (WHERE status='active' AND times_refreshed=0
                                     AND origin='generated'),
                   count(*) FILTER (WHERE status='retired')
            FROM eval_questions GROUP BY 1, 2 ORDER BY 1, 2
            """
        ).fetchall()
        print(f"{'title':>5} {'stratum':<18} {'active':>6} {'core':>5} {'retired':>7}")
        for title, stratum, active, core, ret in rows:
            print(f"{title or '—':>5} {stratum:<18} {active:>6} {core:>5} {ret:>7}")
        totals = conn.execute(
            "SELECT count(*) FILTER (WHERE status='active'), "
            "count(*) FILTER (WHERE status='active' AND times_refreshed=0 "
            "                  AND origin='generated') FROM eval_questions"
        ).fetchone()
        print(f"\nactive: {totals[0]}   stable core: {totals[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Phase 10 Part A eval library")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_seed = sub.add_parser("seed", help="build/extend the library to quotas")
    p_seed.add_argument("--titles", type=int, nargs="+")
    p_seed.add_argument("--scale", type=float, default=1.0,
                        help="quota multiplier (use small values for smoke tests)")
    p_seed.add_argument("--dry-run", action="store_true")

    p_ref = sub.add_parser("refresh", help="post-sync retire/re-reference/top-up")
    p_ref.add_argument("--dry-run", action="store_true")
    p_ref.add_argument("--no-top-up", action="store_true")

    sub.add_parser("status", help="stratum coverage and core size")

    args = ap.parse_args()
    if args.cmd == "seed":
        cmd_seed(args.titles, args.scale, args.dry_run)
    elif args.cmd == "refresh":
        cmd_refresh(args.dry_run, top_up=not args.no_top_up)
    else:
        cmd_status()
