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
    'Relevant' = chunk whose text or citation contains the ground-truth CFR reference.
    """
    if not ground_truth_reference:
        return {"precision_at_k": None, "recall_at_k": None, "mrr": None, "ndcg_at_k": None}

    refs = [r.strip().lower() for r in ground_truth_reference.split("|")]

    def is_relevant(chunk) -> bool:
        haystack = (chunk.chunk_text + chunk.citation_string()).lower()
        return any(ref in haystack for ref in refs)

    hits = [is_relevant(c) for c in retrieved_chunks[:k]]
    relevant_count = sum(hits)

    precision = relevant_count / k if k else 0.0
    recall = relevant_count / len(refs) if refs else 0.0

    mrr = 0.0
    for i, hit in enumerate(hits):
        if hit:
            mrr = 1.0 / (i + 1)
            break

    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal_hits = min(len(refs), k)
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
    top_k = config.get("retrieval", {}).get("top_k", 6)
    source_id_filter = config.get("retrieval", {}).get("source_id_filter")
    title_number = config.get("retrieval", {}).get("title_number")
    source_system = config.get("retrieval", {}).get("source_system", "federal_regulations")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = []
    total_input_tokens = 0
    total_output_tokens = 0

    print(f"[eval] Config: {config['name']}  strategy={strategy}  top_k={top_k}  source_system={source_system}  questions={len(questions)}")

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
        )

        ret_metrics = retrieval_metrics(chunks, q.get("ground_truth_reference", ""), top_k)

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
        gen_result = generate(q["question"], chunks, strategy=strategy)
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
        print(f"[eval] Tokens used:    {total_input_tokens + total_output_tokens}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()
    run_evaluation(args.config, limit=args.limit, skip_generation=args.retrieval_only)
