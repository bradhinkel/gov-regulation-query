# Phase 9.1 — Confidence Calibration Findings

**Goal:** expand the eval set to 200 questions across 8 CFR titles, add a third
confidence component (retrieval concentration), and empirically reweight the
confidence formula by maximizing rank correlation with answer quality.

**Outcome:** a rigorous *negative* result with a clear root cause. Reweighting was
**not** adopted because the data shows it cannot improve the signal — and the
investigation surfaced two concrete, actionable facts.

## Method

- Generated a 200-question dataset, 25 per title across all 8 titles
  (`eval/data/eval_dataset_200.json`).
- Ran the full pipeline (`baseline_200`): retrieval + sequential generation +
  per-question confidence components (retrieval_score, citation_coverage, and the
  new retrieval_concentration) + LLM-judge faithfulness.
- Grid search over all (α, β, γ) weight triples maximizing Spearman ρ between the
  composite and judge faithfulness (`eval/src/optimize_confidence.py`).

## Results

**1. No inference-time signal predicts judge faithfulness.** Best grid-search
ρ ≈ 0.04 (p≈0.57). Per-component Spearman vs the original Haiku faithfulness:

| Signal | ρ vs faithfulness |
|---|---|
| retrieval_score | +0.05 (ns) |
| citation_coverage | −0.05 (ns) — confirms it rewards citation *format*, not grounding |
| retrieval_concentration | **−0.22** (significant, **wrong direction**) |
| semantic_grounding (added LLM check) | −0.03; saturates at mean **0.99** |

**2. The Haiku single-call judge was unreliable.** Inspecting the low-faithfulness
cluster (17 answers scored exactly 0.3) showed answers that **match the
ground-truth reference almost verbatim** — correct and grounded — yet were scored
0.3 faithfulness / 0.2 legal. Re-judging all answers with **Sonnet against the
ground-truth reference** gave only **ρ=0.28 agreement** with the Haiku judge.

**3. Even with the reliable judge, signals still don't correlate.** Against Sonnet
correctness (mean **0.90**, std 0.21): retrieval −0.00, citation −0.01,
grounding −0.10, concentration −0.10. High-vs-low-quality group means differ by
≤0.03 on every signal.

## Interpretation

When the system answers, its answers are **uniformly high quality** (Sonnet
correctness ≈ 0.90) because retrieval is grounded and generation only uses
retrieved context. With little quality *variance* among answered questions, no
inference-time signal has a gradient to predict — and a noisy judge makes it
look even worse. The genuinely valuable, validated confidence primitive is the
**binary `not_found` detection** (26/200 correctly flagged as coverage gaps).

## Decisions (data-driven)

- **retrieval_concentration: computed and exposed as a diagnostic, weight = 0.**
  It is negatively correlated; adding it with a positive weight would *hurt*.
- **No spurious reweighting.** The grid-search "winner" (0.95/0.05/0) is
  noise-level; adopting it would overfit noise. Production keeps the existing
  retrieval+citation diagnostic; the tiers are presented as a grounding/retrieval
  diagnostic with `not_found` as the calibrated primitive — not a calibrated
  quality probability.
- **Eval judge upgraded to Sonnet** (`JUDGE_MODEL`, default `claude-sonnet-4-6`)
  — the Haiku judge is too noisy to serve as ground truth.

## If revisited

A meaningful confidence *gradient* would require quality variance to predict —
e.g., a harder/adversarial question mix, or a different target (answer
completeness vs. a reference) — plus a robust judge (multi-sample or stronger
model). Platt scaling (plan Task 3.5) is moot until a predictive signal exists.
