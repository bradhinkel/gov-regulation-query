"""
eval/src/evaluate.py — Evaluation harness for the Federal Regulation RAG.

For each question in eval/data/eval_dataset.json:
  1. Retrieve top-k chunks
  2. Compute retrieval metrics (Precision@k, Recall@k, MRR, NDCG@k)
  3. Generate three-output response (plain_english, legal_language, citations)
  4. Score with LLM judge: faithfulness, legal_accuracy, citation_accuracy
  5. Track latency and token usage

Results saved to eval/results/{config_name}.json

Usage:
    python eval/src/evaluate.py --config eval/configs/baseline.yaml
    python eval/src/evaluate.py --config eval/configs/baseline.yaml --limit 10
    python eval/src/evaluate.py --config eval/configs/baseline.yaml --retrieval-only
"""

import argparse
import json
import math
import os
import sys
import time

import anthropic
import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.query import retrieve
from src.generate import generate

EVAL_DATASET = os.path.join(PROJECT_ROOT, "eval", "data", "eval_dataset.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "eval", "results")

JUDGE_MODEL = "claude-haiku-4-5-20251001"

_anthropic = anthropic.Anthropic()


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_dataset(limit: int | None = None) -> list:
    with open(EVAL_DATASET) as f:
        data = json.load(f)
    questions = data["questions"]
    if limit:
        questions = questions[:limit]
    return questions


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def retrieval_metrics(retrieved_chunks: list, ground_truth_reference: str, k: int) -> dict:
    """
    Precision@k, Recall@k, MRR@k, NDCG@k.
    'Relevant' = chunk whose CFR citation metadata matches the ground-truth section.

    Matching rules:
    - Sub-paragraph notation in ground truth (e.g. '§ 205.301(a)(1)') is stripped to the
      base section ('§ 205.301') before matching, since chunk metadata stores only the
      section-level reference.
    - Matching is against citation_string() ONLY, not chunk_text. Regulatory text frequently
      contains cross-references (e.g. "See § 135.110 for definitions") that would create
      false positives if the full text were searched.
    - ideal_hits for NDCG is the number of unique base sections in the ground truth,
      ensuring NDCG stays in [0, 1].
    """
    import re as _re

    if not ground_truth_reference:
        return {"precision_at_k": None, "recall_at_k": None, "mrr": None, "ndcg_at_k": None}

    def _base_ref(ref: str) -> str:
        """Strip paragraph sub-identifiers like (a)(1)(i), (84), 'and (c)' from a CFR ref."""
        return _re.split(r'\s+and\s+|\(', ref.strip())[0].strip()

    raw_refs = [r.strip() for r in ground_truth_reference.split("|") if r.strip()]
    # Use only base section refs for matching; deduplicate in case two raw refs share a base
    base_refs = {_base_ref(r).lower() for r in raw_refs}

    # Deduplicate by section: each ground-truth section can contribute at most
    # one "hit" regardless of how many paragraph chunks from that section appear
    # in the retrieved list. Without dedup, multiple paragraph chunks from the
    # same section inflate DCG beyond IDCG, making NDCG > 1 (physically impossible).
    seen_sections: set = set()

    def is_relevant_dedup(chunk) -> bool:
        """Return True only for the FIRST chunk from each matched ground-truth section."""
        citation = chunk.citation_string().lower()
        for br in base_refs:
            if br in citation:
                if br not in seen_sections:
                    seen_sections.add(br)
                    return True
                return False  # duplicate section — don't credit again
        return False

    hits = [is_relevant_dedup(c) for c in retrieved_chunks[:k]]
    relevant_count = sum(hits)  # = number of unique ground-truth sections found

    precision = relevant_count / k if k else 0.0
    recall = relevant_count / len(base_refs) if base_refs else 0.0

    mrr = 0.0
    for i, hit in enumerate(hits):
        if hit:
            mrr = 1.0 / (i + 1)
            break

    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    # ideal_hits: best case = all ground-truth sections appear in top-k positions
    ideal_hits = min(len(base_refs), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    ndcg = dcg / idcg if idcg else 0.0

    return {
        "precision_at_k": round(precision, 4),
        "recall_at_k": round(recall, 4),
        "mrr": round(mrr, 4),
        "ndcg_at_k": round(ndcg, 4),
    }


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """\
You are evaluating a federal regulation RAG system. Score each dimension 0.0–1.0.
Respond with ONLY a JSON object — no explanation."""


def judge_response(
    question: str,
    ground_truth: str,
    plain_english: str,
    legal_language: str,
    context_chunks: list,
    citations: list,
) -> dict:
    context_text = "\n\n".join(
        f"[{c.citation_string()}]\n{c.chunk_text[:400]}" for c in context_chunks
    )
    citation_strs = [c.citation_string() for c in citations] if citations else []

    prompt = f"""{_JUDGE_SYSTEM}

Question: {question}
Ground Truth: {ground_truth}

Retrieved Context (abbreviated):
{context_text[:2000]}

Plain English Answer: {plain_english}
Legal Language Answer: {legal_language}
Citations: {json.dumps(citation_strs)}

Score these dimensions:
1. faithfulness (0–1): Is plain_english grounded in the context? 1.0=fully grounded, 0.0=hallucinated.
2. answer_relevancy (0–1): Does plain_english address the question? 1.0=fully relevant.
3. legal_accuracy (0–1): Does legal_language correctly use formal regulatory register with accurate verbatim quotes? 1.0=excellent.
4. citation_accuracy (0–1): Do the citations match sources actually used to answer? 1.0=all correct.
5. answer_completeness (0–1): Does plain_english fully address the question given the context? 1.0=complete.

Respond with ONLY:
{{"faithfulness": <float>, "answer_relevancy": <float>, "legal_accuracy": <float>, "citation_accuracy": <float>, "answer_completeness": <float>}}"""

    response = _anthropic.messages.create(
        model=JUDGE_MODEL,
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {k: 0.0 for k in ["faithfulness", "answer_relevancy", "legal_accuracy", "citation_accuracy", "answer_completeness"]}


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_evaluation(config_path: str, limit: int | None = None, skip_generation: bool = False):
    config = load_config(config_path)
    questions = load_dataset(limit)

    strategy = config.get("generation", {}).get("strategy", "sequential")
    model = config.get("generation", {}).get("model", "claude-haiku-4-5-20251001")
    top_k = config.get("retrieval", {}).get("top_k", 6)
    # eval_top_k overrides the k used for NDCG/Precision metrics — useful when
    # hierarchical retrieval returns fewer chunks than the retrieval top_k.
    eval_top_k = config.get("eval_top_k", top_k)
    search_mode = config.get("retrieval", {}).get("search_mode", "vector")
    query_rewrite = config.get("retrieval", {}).get("query_rewrite", False)
    source_id_filter = config.get("retrieval", {}).get("source_id_filter")
    title_number = config.get("retrieval", {}).get("title_number")
    source_system = config.get("retrieval", {}).get("source_system", "federal_regulations")
    max_sections = config.get("retrieval", {}).get("max_sections", 6)
    max_chars_per_section = config.get("retrieval", {}).get("max_chars_per_section", 4000)
    use_hyde = config.get("retrieval", {}).get("use_hyde", False)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = []
    total_input_tokens = 0
    total_output_tokens = 0

    hier_info = f"  max_sections={max_sections}  max_chars={max_chars_per_section}" if search_mode == "hierarchical" else ""
    hyde_info = "  hyde=True" if use_hyde else ""
    print(f"[eval] Config: {config['name']}  strategy={strategy}  model={model}  search_mode={search_mode}  query_rewrite={query_rewrite}{hyde_info}  top_k={top_k}  eval_top_k={eval_top_k}{hier_info}  questions={len(questions)}")

    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q['id']} — {q['question'][:70]}...")

        # Retrieve
        t0 = time.time()
        chunks, timing = retrieve(
            q["question"],
            top_k=top_k,
            source_system=source_system,
            title_number=title_number,
            source_id=source_id_filter,
            search_mode=search_mode,
            query_rewrite=query_rewrite,
            use_hyde=use_hyde,
            max_sections=max_sections,
            max_chars_per_section=max_chars_per_section,
        )

        ret_metrics = retrieval_metrics(chunks, q.get("ground_truth_reference", ""), eval_top_k)

        if skip_generation:
            results.append({
                "id": q["id"],
                "question": q["question"],
                "ground_truth": q.get("ground_truth"),
                "num_chunks": len(chunks),
                "retrieval_metrics": ret_metrics,
                "generation_scores": None,
                "timing": timing,
            })
            continue

        # Generate
        gen_result = generate(q["question"], chunks, strategy=strategy, model=model)
        timing["generation_ms"] = gen_result.latency_ms
        timing["e2e_ms"] = (time.time() - t0) * 1000
        total_input_tokens += gen_result.input_tokens
        total_output_tokens += gen_result.output_tokens

        qr = gen_result.response
        if qr.not_found:
            gen_scores = {k: 0.0 for k in ["faithfulness", "answer_relevancy", "legal_accuracy", "citation_accuracy", "answer_completeness"]}
            gen_scores["not_found"] = True
        else:
            gen_scores = judge_response(
                q["question"],
                q.get("ground_truth", ""),
                qr.plain_english,
                qr.legal_language,
                chunks,
                qr.citations,
            )
            gen_scores["not_found"] = False

        conf = gen_result.confidence
        results.append({
            "id": q["id"],
            "question": q["question"],
            "ground_truth": q.get("ground_truth"),
            "ground_truth_reference": q.get("ground_truth_reference"),
            "plain_english": qr.plain_english,
            "legal_language": qr.legal_language,
            "citations": [c.model_dump() for c in qr.citations],
            "strategy_used": qr.strategy_used,
            "num_chunks": len(chunks),
            "retrieval_metrics": ret_metrics,
            "generation_scores": gen_scores,
            "confidence": {
                "score": conf.score,
                "tier": conf.tier,
                "retrieval_score": conf.retrieval_score,
                "citation_coverage": conf.citation_coverage,
                "verified_citations": conf.verified_citations,
                "unverified_citations": conf.unverified_citations,
            } if conf else None,
            "timing": {k: round(v, 1) for k, v in timing.items()},
            "tokens": {"input": gen_result.input_tokens, "output": gen_result.output_tokens},
        })

    # Aggregate
    def avg(key, subkey):
        vals = [r[key][subkey] for r in results if r.get(key) and r[key].get(subkey) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    summary = {
        "config": config["name"],
        "strategy": strategy,
        "model": model,
        "search_mode": search_mode,
        "query_rewrite": query_rewrite,
        "top_k": top_k,
        "source_system": source_system,
        "num_questions": len(results),
        "retrieval": {
            "avg_precision_at_k": avg("retrieval_metrics", "precision_at_k"),
            "avg_recall_at_k":    avg("retrieval_metrics", "recall_at_k"),
            "avg_mrr":            avg("retrieval_metrics", "mrr"),
            "avg_ndcg_at_k":      avg("retrieval_metrics", "ndcg_at_k"),
        },
        "generation": {
            "avg_faithfulness":        avg("generation_scores", "faithfulness"),
            "avg_answer_relevancy":    avg("generation_scores", "answer_relevancy"),
            "avg_legal_accuracy":      avg("generation_scores", "legal_accuracy"),
            "avg_citation_accuracy":   avg("generation_scores", "citation_accuracy"),
            "avg_answer_completeness": avg("generation_scores", "answer_completeness"),
        },
        "confidence": {
            "avg_score":             avg("confidence", "score"),
            "avg_retrieval_score":   avg("confidence", "retrieval_score"),
            "avg_citation_coverage": avg("confidence", "citation_coverage"),
            "tier_counts": {
                tier: sum(1 for r in results if r.get("confidence", {}) and r["confidence"].get("tier") == tier)
                for tier in ("high", "medium", "low", "not_found")
            },
        },
        "timing": {
            "avg_embed_ms":      avg("timing", "embed_ms"),
            "avg_retrieve_ms":   avg("timing", "retrieve_ms"),
            "avg_generation_ms": avg("timing", "generation_ms"),
            "avg_e2e_ms":        avg("timing", "e2e_ms"),
        },
        "tokens": {
            "total_input":  total_input_tokens,
            "total_output": total_output_tokens,
        },
    }

    output = {"summary": summary, "results": results}
    out_path = os.path.join(RESULTS_DIR, f"{config['name']}.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[eval] Done. Results → {out_path}")
    print(f"[eval] MRR:         {summary['retrieval']['avg_mrr']}")
    print(f"[eval] NDCG@k:      {summary['retrieval']['avg_ndcg_at_k']}")
    if not skip_generation:
        print(f"[eval] Faithfulness:   {summary['generation']['avg_faithfulness']}")
        print(f"[eval] Legal Accuracy: {summary['generation']['avg_legal_accuracy']}")
        print(f"[eval] Citation Acc:   {summary['generation']['avg_citation_accuracy']}")
        tiers = summary["confidence"]["tier_counts"]
        print(f"[eval] Confidence:     avg={summary['confidence']['avg_score']}  "
              f"high={tiers['high']}  medium={tiers['medium']}  low={tiers['low']}  not_found={tiers['not_found']}")
        print(f"[eval] Tokens used:    {total_input_tokens + total_output_tokens}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()
    run_evaluation(args.config, limit=args.limit, skip_generation=args.retrieval_only)
