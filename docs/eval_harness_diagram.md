# Evaluation Harness — Per-Question Data Flow

Diagram of `eval/src/evaluate.py`. Each of the 60 questions in `eval_dataset.json` flows through the pipeline once per config run; retrieval and generation are scored through two independent metric paths (deterministic vs. LLM-as-judge).

**Orange = LLM call** (cost, latency, rubric risk live here).
**Green = deterministic** (cheap, reproducible).
**Dashed edges** carry ground truth into the metric layer.

```mermaid
flowchart LR
  %% ─── INPUTS ───
  subgraph INPUTS["INPUTS"]
    direction TB
    YAML["<b>YAML config</b><br/>retrieval.*<br/>generation.*<br/>eval_top_k"]
    DATASET["<b>eval_dataset.json</b><br/>60 questions, each with:<br/>• question<br/>• ground_truth<br/>• ground_truth_reference"]
  end

  %% ─── PIPELINE ───
  subgraph PIPELINE["PIPELINE UNDER TEST — loop over 60 questions"]
    direction TB
    RETRIEVE["<b>retrieve()</b><br/>top_k, search_mode,<br/>query_rewrite, use_hyde,<br/>source_system, title_number"]
    CHUNKS(["chunks"])
    GENERATE["<b>generate()</b><br/>strategy, model"]
    ANSWER(["plain_english<br/>legal_language<br/>citations<br/>not_found flag"])
    TIMING[/"timing + token counter"/]
    RETRIEVE --> CHUNKS --> GENERATE --> ANSWER
  end

  %% ─── METRICS ───
  subgraph METRICS["METRICS"]
    direction TB
    RETMETRICS["<b>retrieval_metrics()</b><br/><i>deterministic</i><br/>Precision@k, Recall@k,<br/>MRR, NDCG@k"]
    SHORTCIRCUIT{"not_found?"}
    JUDGE["<b>judge_response()</b><br/><i>LLM-as-judge · Haiku 4.5</i><br/>faithfulness, answer_relevancy,<br/>legal_accuracy, citation_accuracy,<br/>answer_completeness"]
    ZEROS[/"scores = 0.0"/]
  end

  %% ─── OUTPUT ───
  subgraph OUTPUT["OUTPUT"]
    direction TB
    PERQ["per-question<br/>results (×60)"]
    SUMMARY["aggregate summary<br/>averages, totals,<br/>tier counts"]
    JSON[("results/&lt;config_name&gt;.json")]
    PERQ --> SUMMARY --> JSON
  end

  %% ─── WIRING ───
  YAML -->|"retrieval.*"| RETRIEVE
  YAML -->|"generation.*"| GENERATE
  DATASET -->|"question"| RETRIEVE
  DATASET -->|"question"| GENERATE
  DATASET -.->|"ground_truth_reference<br/>(CFR citation)"| RETMETRICS
  DATASET -.->|"ground_truth<br/>(answer text)"| JUDGE

  CHUNKS --> RETMETRICS
  CHUNKS --> JUDGE
  ANSWER --> SHORTCIRCUIT
  SHORTCIRCUIT -->|"yes"| ZEROS
  SHORTCIRCUIT -->|"no"| JUDGE
  TIMING --> PERQ

  RETMETRICS --> PERQ
  JUDGE --> PERQ
  ZEROS --> PERQ

  %% ─── STYLING ───
  classDef llm fill:#fde7cc,stroke:#c47a2d,stroke-width:2px,color:#000
  classDef det fill:#e6f3e6,stroke:#2e7d32,stroke-width:1px,color:#000
  classDef data fill:#e8eef7,stroke:#30568f,stroke-width:1px,color:#000
  classDef flow fill:#ffffff,stroke:#999999,stroke-width:1px,color:#000
  classDef output fill:#f2e8f7,stroke:#6a3d8b,stroke-width:1px,color:#000

  class GENERATE,JUDGE llm
  class RETMETRICS,SHORTCIRCUIT det
  class YAML,DATASET data
  class CHUNKS,ANSWER,TIMING flow
  class PERQ,SUMMARY,JSON output
```

## Notes

- **Ground truth splits two ways.** `ground_truth_reference` (a CFR section citation) is matched deterministically against `chunk.citation_string()` in `retrieval_metrics()`. `ground_truth` (the reference answer text) is passed to the LLM judge as the comparison target for faithfulness and legal accuracy.
- **`not_found` short-circuits the judge.** When the generator returns `not_found=True`, all five generation scores are hardcoded to `0.0` — this is why every not-found row in the results has `faithfulness=0.000` exactly. That zero is by construction, not a measurement.
- **Two independent cost profiles.** The retrieval path is free and reproducible. The judge path is one Haiku call per non-not-found question — ~60 extra calls per config run, plus the generation calls themselves.
- **Not shown (intentional):** confidence scoring, hierarchical retrieval's `max_sections` / `max_chars_per_section` assembly, HyDE query expansion, and the `--retrieval-only` fast path. They exist in the code but are orthogonal to the primary flow.
