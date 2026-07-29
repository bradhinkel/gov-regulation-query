"""
eval/src/eval_partc_forward.py — Part C forward-looking answer quality
(docx C.7): status-label correctness (target 100%), comment-window accuracy,
and judge-scored grounding against the retrieved FR documents (same bar as
codified answers, mean grounding >= 0.75 normalized).

Cases are built live: for a set of forward-looking queries over corpus CFR
parts, fetch current Federal Register documents, generate the forward answer,
then check:
  status_label   — the answer carries an explicit non-binding label
                   (proposed/pending/comment period/not yet ...)
  comment_window — if a cited document has a comment close date, the answer
                   states that exact date (checked against the live API value)
  grounding      — src/judge.py in forward mode over the same documents
                   (which also enforces the label rule: grounding capped at 2
                   on an unlabeled proposed claim)

Usage:  python eval/src/eval_partc_forward.py
"""

import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.sources import fetch_forward_documents           # noqa: E402
from src.generate import generate_forward                 # noqa: E402
from src.judge import judge_grounding                     # noqa: E402
from src.escalation import _FRDocChunk                    # noqa: E402

_LABEL_RE = re.compile(
    r"proposed|pending|comment period|not yet (law|in effect|codified|final)", re.I)

# (query, cfr_parts hint) — parts mirror what production retrieval would find.
CASES = [
    ("What changes are being proposed to the National Organic Program allowed substances list?",
     [(7, "205")]),
    ("Are stricter air quality standards being proposed under the Clean Air Act?",
     [(40, "50"), (40, "52")]),
    ("What new rules is FDA proposing for food safety?",
     [(21, "112"), (21, "117")]),
    ("Are there upcoming changes to commercial driver hours-of-service rules?",
     [(49, "395")]),
    ("What Medicare payment rule changes are being proposed?",
     [(42, "414"), (42, "410")]),
    ("Is OSHA proposing any new workplace safety standards?",
     [(29, "1910")]),
]


def _date_variants(iso: str) -> list[str]:
    """The close date in the formats an answer might reasonably use."""
    d = date.fromisoformat(iso)
    return [
        iso,
        d.strftime("%B %-d, %Y") if sys.platform != "win32" else d.strftime("%B %d, %Y"),
        d.strftime("%B %d, %Y"),
        d.strftime("%b %d, %Y"),
    ]


def main() -> int:
    label_ok, window_ok, window_n, groundings = [], [], 0, []
    for i, (query, parts) in enumerate(CASES):
        payload = fetch_forward_documents(query, cfr_parts=parts)
        docs = payload["documents"]
        if not docs:
            print(f"  [{i+1}/{len(CASES)}] no FR documents — skipped: {query[:60]}")
            continue
        gen = generate_forward(query, payload)
        if gen is None:
            print(f"  [{i+1}/{len(CASES)}] generator declined (not_found) — skipped")
            continue
        answer = gen.response.plain_english

        # 1. Status label present?
        labeled = bool(_LABEL_RE.search(answer))
        label_ok.append(labeled)

        # 2. Comment-window accuracy: for cited docs with a close date, the
        #    answer must state that date. "Cited" = FR citation appears.
        window_hits = window_misses = 0
        for d in docs:
            cite = d.get("fr_citation") or ""
            if not cite or cite not in answer or not d.get("comments_close_on"):
                continue
            window_n += 1
            if any(v in answer for v in _date_variants(d["comments_close_on"])):
                window_hits += 1
                window_ok.append(True)
            else:
                window_misses += 1
                window_ok.append(False)

        # 3. Judge in forward mode over the same documents.
        verdict = judge_grounding(query, answer, [_FRDocChunk(d) for d in docs],
                                  forward_looking=True)
        g = verdict.grounding_norm
        if g is not None:
            groundings.append(g)

        print(f"  [{i+1}/{len(CASES)}] label={'Y' if labeled else 'N'} "
              f"windows={window_hits}/{window_hits + window_misses} "
              f"grounding={verdict.grounding}  {query[:55]}")

    if not label_ok:
        print("[forward] no cases produced answers — cannot evaluate")
        return 1

    # Seeded negative (docx C.5): strip the status labels from one real answer
    # and confirm the forward-mode judge CATCHES it (grounding capped <= 2).
    payload = fetch_forward_documents(CASES[0][0], cfr_parts=CASES[0][1])
    gen = generate_forward(CASES[0][0], payload)
    seeded_caught = None
    if gen:
        stripped = re.sub(
            r"\[[^\]]*(proposed|pending|comment|not yet)[^\]]*\]|"
            r"\b(proposed|proposal|proposing|pending|not yet \w+|comment period[^.]*)\b",
            "", gen.response.plain_english, flags=re.I)
        stripped = re.sub(r"\n\nComment windows:.*", "", stripped, flags=re.S)
        v = judge_grounding(CASES[0][0], stripped,
                            [_FRDocChunk(d) for d in payload["documents"]],
                            forward_looking=True)
        seeded_caught = v.grounding is not None and v.grounding <= 2
        print(f"\n[forward] seeded unlabeled answer: judge grounding={v.grounding} "
              f"-> {'CAUGHT' if seeded_caught else 'MISSED'}")

    label_rate = sum(label_ok) / len(label_ok)
    window_rate = (sum(window_ok) / len(window_ok)) if window_ok else None
    g_mean = sum(groundings) / len(groundings) if groundings else None
    print(f"\n[forward] status-label correctness: {label_rate:.0%} "
          f"(target 100%) {'PASS' if label_rate == 1.0 else 'FAIL'}")
    print(f"[forward] comment-window accuracy: "
          f"{f'{window_rate:.0%} over {window_n} cited windows' if window_rate is not None else 'n/a (no cited windows)'}")
    print(f"[forward] mean judge grounding: "
          f"{f'{g_mean:.3f}' if g_mean is not None else 'n/a'} "
          f"(codified bar ~0.75+)")
    ok = label_rate == 1.0 and (seeded_caught is not False)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
