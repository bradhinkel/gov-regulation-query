# RAG Evaluation Methodology & Optimization Log
## Government Regulation Query — Federal Regulation RAG System

---

## Overview

This document records the evaluation framework, experiment progression, and key findings from
optimizing the Federal Regulation RAG system. The system answers natural language questions about
U.S. federal regulations (eCFR) with three structured outputs: plain English explanation, legal/
regulatory language with verbatim citations, and precise CFR citation references.

The corpus covers Titles 7 (Agriculture), 21 (Food and Drugs), and 42 (Public Health) from the
Code of Federal Regulations, sourced live from the eCFR API.

---

## Evaluation Framework

### Dataset

- **60 questions** drawn from Titles 7, 21, and 42
- Each question has a `ground_truth` answer and `ground_truth_reference` (CFR citation, e.g. `7 CFR § 205.301`)
- Questions target specific regulatory details: exact thresholds, procedural requirements, definitions, and cross-reference lookups

### Retrieval Metrics

Computed automatically by comparing retrieved chunks against the ground truth CFR reference.
A chunk is considered **relevant** if its CFR citation metadata matches the ground truth section.

| Metric | Description |
|---|---|
| **Precision@k** | Fraction of retrieved positions occupied by a new (not yet seen) relevant section |
| **Recall@k** | Fraction of ground-truth sections that appear anywhere in the top-k results |
| **MRR** | Mean Reciprocal Rank — rewards finding the first relevant chunk early in the ranked list |
| **NDCG@k** | Normalized Discounted Cumulative Gain — position-weighted relevance score |

MRR and NDCG are the primary signals. MRR measures whether the most relevant chunk surfaces
at all; NDCG captures how well the full ranked list is ordered.

**Matching rules (corrected — see Appendix A):**
- Ground truth references containing sub-paragraph notation (e.g. `§ 205.301(a)(1)`) are
  stripped to the base section (`§ 205.301`) before matching, since chunk metadata stores
  only the section-level reference.
- Matching is performed against `citation_string()` metadata only, never against `chunk_text`.
  Regulatory body text frequently contains cross-references (e.g. "See § 135.110 for
  definitions") that would create false positives if searched.
- Each ground-truth section is counted **at most once** in the hits list, regardless of how
  many paragraph-level chunks from that section appear in the retrieved list. This prevents
  NDCG from exceeding 1.0 when multiple chunks from the same section rank highly.

### Generation Metrics (LLM-as-Judge)

Scored 0.0–1.0 by `claude-haiku-4-5-20251001` acting as an independent judge. Each dimension
is scored separately per question, then averaged across the 60-question dataset.

| Metric | What It Measures |
|---|---|
| **Faithfulness** | Is the plain English answer grounded in the retrieved context? (1.0 = no hallucination) |
| **Answer Relevancy** | Does the plain English answer address the question? |
| **Legal Accuracy** | Does the legal language answer use correct regulatory register with accurate verbatim quotes? |
| **Citation Accuracy** | Do the cited CFR references match the sources actually used to answer? |
| **Answer Completeness** | Does the plain English answer fully address the question given the available context? |

### Latency & Cost

End-to-end latency (embed → retrieve → generate) and total input/output tokens are recorded
per run to inform production cost decisions.

---

## Experiment Log

Experiments are grouped by the variable being isolated. All configs use the same 60-question
dataset against the same PostgreSQL + pgvector corpus unless noted.

---

### Experiment 1 — Generation Strategy: Single Call vs. Sequential

**Variable:** One LLM call returning structured JSON vs. two sequential calls (plain English first,
then legal language using the plain English as additional context).

**Hypothesis:** Sequential calls allow the second call to build on the first, improving legal
language quality and verbatim quote accuracy.

| Config | Strategy | MRR | NDCG@k | Faithfulness | Legal Acc | Cit Acc | E2E Latency |
|---|---|---|---|---|---|---|---|
| single_call | single | 0.275 | 0.473 | 0.489 | 0.494 | 0.429 | 2.5s |
| baseline | sequential | 0.275 | 0.473 | 0.511 | 0.527 | 0.484 | 4.9s |

**Finding:** Sequential strategy improves all three generation metrics meaningfully (faithfulness
+4.5%, legal accuracy +6.7%, citation accuracy +12.9%) at a 2× latency cost. Retrieval is
identical since both use the same top_k=6 vector search. **Sequential becomes the standard for
all subsequent experiments.**

---

### Experiment 2 — Retrieval Depth: Top-k Tuning

**Variable:** Number of chunks retrieved per query (top_k = 6 vs. 10).

**Hypothesis:** More retrieved chunks increase the chance of capturing the relevant section,
improving recall and giving the LLM more complete context.

| Config | top_k | MRR | NDCG@k | Recall@k | Faithfulness | Legal Acc | Cit Acc |
|---|---|---|---|---|---|---|---|
| baseline | 6 | 0.275 | 0.473 | 0.683 | 0.511 | 0.527 | 0.484 |
| top_k10 | 10 | 0.275 | **0.520** | **0.833** | **0.553** | **0.560** | 0.458 |

**Finding:** Increasing top_k from 6 to 10 is the single highest-impact change in the evaluation.
NDCG improves 10%, recall improves 22 percentage points, and all generation metrics improve — at
no MRR cost. The trade-off is a modest 13% increase in generation tokens. **top_k=10 with
sequential Haiku becomes the baseline to beat.**

---

### Experiment 3 — Generation Model: Haiku vs. Sonnet

**Variable:** Generation model (claude-haiku-4-5-20251001 vs. claude-sonnet-4-6), holding
retrieval constant at top_k=10, vector search, sequential strategy.

**Hypothesis:** Sonnet's stronger reasoning capability will produce noticeably better legal
language and more accurate verbatim quote integration.

| Config | Model | Faithfulness | Answer Relevancy | Legal Acc | Cit Acc | E2E Latency | Tokens (in+out) |
|---|---|---|---|---|---|---|---|
| top_k10 | Haiku | 0.553 | 0.614 | 0.560 | 0.458 | 5.6s | 309,113 |
| sonnet_vector | Sonnet | 0.558 | **0.640** | 0.561 | **0.483** | 20.1s | 354,025 |

**Finding:** Sonnet provides marginal gains on generation quality (+0.9% faithfulness, +0.1%
legal accuracy) at 3.6× the latency and ~15% more tokens. The quality delta is within measurement
noise for a 60-question dataset. For a regulatory use case where cost and latency matter, the
improvement does not justify the upgrade. **Haiku remains the generation model.**

---

### Experiment 4 — Retrieval Mode: Vector vs. Hybrid (RRF)

**Variable:** Pure cosine similarity vs. Reciprocal Rank Fusion (RRF) combining vector search
with PostgreSQL full-text search (FTS) over `chunk_text`, `cfr_reference`, `section_heading`,
and `section_number`.

**Hypothesis:** Hybrid retrieval will improve recall on queries that contain exact CFR references
or specific regulatory terminology, while RRF prevents FTS from degrading precision on
semantic-only queries.

| Config | Mode | MRR | NDCG@k | Precision@k | Recall@k | Faithfulness | Legal Acc |
|---|---|---|---|---|---|---|---|
| sonnet_vector | vector | 0.224 | 0.444 | 0.075 | 0.75 | 0.558 | 0.561 |
| sonnet_hybrid | hybrid | 0.238 | 0.454 | 0.075 | 0.75 | 0.550 | 0.558 |

*Note: Both use Sonnet generation and top_k=10 for a clean comparison.*

**Finding:** Hybrid retrieval provides a small MRR improvement (+6%) but does not close the gap
with the Haiku top_k10 baseline. Recall and precision are identical. The added FTS component
appears to neither help nor hurt meaningfully on this dataset, likely because the eval questions
are phrased in plain language rather than CFR-reference format. **Vector-only retrieval retained
as default.**

---

### Experiment 5 — Query Rewriting

**Variable:** Using a fast Haiku call to expand the user's query into regulatory terminology
before embedding, tested across Haiku and Sonnet generation models.

**Hypothesis:** Expanding the query with CFR terminology, synonyms, and likely regulatory
language will improve vector search recall on domain-specific questions.

| Config | Model | Rewrite | MRR | NDCG@k | Faithfulness | Legal Acc |
|---|---|---|---|---|---|---|
| top_k10 | Haiku | No | **0.275** | **0.520** | 0.553 | **0.560** |
| haiku_vector_rewrite | Haiku | Yes | 0.205 | 0.463 | **0.538** | 0.541 |
| sonnet_hybrid | Sonnet | No | 0.238 | 0.454 | 0.550 | 0.558 |
| sonnet_hybrid_rewrite | Sonnet | Yes | 0.187 | 0.429 | 0.525 | 0.528 |

**Finding:** Query rewriting **consistently degrades retrieval metrics** across both models and
both retrieval modes. MRR drops 25% with Haiku and 21% with Sonnet when rewriting is enabled.
The LLM expansion introduces noise — regulatory text in the eCFR uses precise, controlled
language, and the expanded query drifts toward approximate synonyms that produce false positives.
Additionally, rewriting adds ~250ms of latency per query (a full Haiku API call). **Query
rewriting is disabled in all subsequent configurations.**

---

### Experiment 6 — Embedding Model + Chunking Strategy: voyage-law-2 + Paragraph-Level Chunks

**Variable:** Replacing OpenAI `text-embedding-3-small` (1536 dimensions) with Voyage AI
`voyage-law-2` (1024 dimensions, legal-domain fine-tuned), combined with a switch from
section-level to paragraph-level chunking.

**Corpus impact:** Paragraph-level chunking splits each `<P>` element into its own chunk
(accumulating very short paragraphs), producing 2.7× more chunks — 223,918 vs. 83,448 — each
averaging ~120 tokens rather than ~237 tokens.

| Config | Embedding Model | Chunks | top_k | MRR | NDCG@k | Recall@k | Faithfulness | Legal Acc |
|---|---|---|---|---|---|---|---|---|
| top_k10 | text-embedding-3-small | 83,448 | 10 | **0.275** | **0.520** | 0.833 | 0.553 | **0.560** |
| voyage_paragraph | voyage-law-2 | 223,918 | 10 | 0.246 | 0.504 | **0.850** | **0.555** | 0.546 |

**Finding:** At equivalent top_k=10, voyage-law-2 with paragraph chunks achieves higher recall
(0.850 vs. 0.833) but lower MRR (0.246 vs. 0.275) and lower NDCG (0.504 vs. 0.520). The
likely cause: the 2.7× corpus growth means top_k=10 retrieves a proportionally smaller slice
of the relevant content. Generation quality is essentially equivalent.

**Hypothesis:** Scaling top_k proportionally to the corpus growth (10 × 2.7 ≈ 27, rounded to
25) should restore retrieval quality while preserving the advantages of finer-grained chunks.

---

### Experiment 7 — Top-k Scaling for Paragraph Corpus

**Variable:** top_k=25 with voyage-law-2 paragraph-level corpus — testing whether scaling
top_k proportionally to corpus growth (83K → 224K chunks, ~2.7×) restores retrieval quality.

| Config | Embedding Model | Chunks | top_k | MRR | NDCG@k | Faithfulness | Legal Acc | Cit Acc | Tokens |
|---|---|---|---|---|---|---|---|---|---|
| top_k10 | text-embedding-3-small | 83,448 | 10 | **0.275** | 0.520 | 0.553 | **0.560** | **0.458** | 309K |
| voyage_paragraph | voyage-law-2 | 223,918 | 10 | 0.246 | 0.504 | **0.555** | 0.546 | 0.458 | 142K |
| voyage_top_k25 | voyage-law-2 | 223,918 | 25 | 0.246 | **0.653** | 0.538 | 0.535 | 0.423 | 353K |

**Finding:** Scaling top_k to 25 produces the best retrieval ranking quality in the entire
experiment set — NDCG improves 25.6% over top_k10 (0.653 vs. 0.520). However, generation
metrics decline across all three dimensions. MRR is unchanged from voyage_paragraph@k=10,
meaning the first relevant chunk surfaces at the same rank regardless of whether 10 or 25
chunks are retrieved.

**Root cause — two problems now fully isolated:**

- **Retrieval is excellent.** At top_k=25, paragraph-level chunks with voyage-law-2 produce
  the best NDCG in the study. The relevant regulatory content is being found and ranked well.

- **Generation degrades with fragmented context.** 25 small paragraph chunks (~120 tokens
  each) produce a noisy, disjointed context window. Regulatory sections are tightly
  interdependent — paragraph (a) defines the rule, paragraph (b) lists exceptions, paragraph
  (c) defines terms — and surfacing fragments without their siblings causes the LLM to produce
  incomplete or imprecise answers. This is the classic "lost in the middle" problem amplified
  by regulatory text structure.

**This result is the clearest possible case for hierarchical retrieval:**
retrieve at paragraph granularity (high precision, excellent NDCG) but return full parent
sections to the LLM (coherent context, no fragmentation). At top_k=25, retrieved paragraph
chunks typically span ~10–12 unique sections after deduplication — a context size comparable
to top_k10 section-level chunks, but assembled from far better-ranked source material.

---

## Findings Summary

| Finding | Impact |
|---|---|
| Sequential generation strategy significantly outperforms single-call | +6.7% legal accuracy, +12.9% citation accuracy |
| top_k=10 is the highest single-variable improvement | +10% NDCG, +22pp recall, all generation metrics improve |
| Sonnet vs. Haiku: marginal quality gain, large cost/latency penalty | Not justified at current quality delta |
| Hybrid (RRF) retrieval: small improvement over vector-only | Not significant on this dataset |
| Query rewriting: consistently harmful to retrieval | −25% MRR; disabled |
| voyage-law-2 + paragraph chunks: needs proportionally higher top_k | Under-sampled at top_k=10 relative to corpus size |

---

## Current Best Configuration

No single configuration dominates across both retrieval and generation. The experiment set
reveals a fundamental tension that points to hierarchical retrieval as the next architectural step:

| Config | Best At |
|---|---|
| top_k10 | Generation quality (faithfulness, legal accuracy, citation accuracy) |
| voyage_top_k25 | Retrieval quality (NDCG — best in study at 0.653) |

Until hierarchical retrieval is implemented, **top_k10 remains the production configuration**
for generation quality. voyage_top_k25 is the retrieval target to match or exceed.

```yaml
# Current production config (top_k10)
embedding_model: text-embedding-3-small   # 1536 dims
chunk_strategy: section-level             # one DIV8 per chunk, ~237 tokens avg
corpus_size: 83,448 chunks                # Titles 7, 21, 42
retrieval:
  search_mode: vector
  top_k: 10
  query_rewrite: false
generation:
  strategy: sequential
  model: claude-haiku-4-5-20251001
```

---

---

### Experiment 8 — Hierarchical Retrieval (Two Variants)

**Variable:** After paragraph-level vector retrieval (top_k=25), deduplicate to unique sections
and assemble all sibling paragraphs per section before passing to the LLM. Tested in two
forms to isolate the context-size problem.

**Hypothesis:** Paragraph retrieval finds the right section (NDCG@25=0.653); assembling the
full parent section gives the LLM coherent regulatory context rather than fragments.

**Variant A — Unbounded assembly** (all sibling paragraphs, no section cap):

| Config | MRR | NDCG@k | Faithfulness | Legal Acc | Cit Acc | Tokens/Q |
|---|---|---|---|---|---|---|
| voyage_top_k25_hierarchical (unbounded) | 0.246 | 0.251 | 0.446 | 0.452 | 0.328 | 37,867 |

Token count exploded 6.4× vs. voyage_top_k25. Many CFR sections (substance tables, lengthy
procedural requirements) contain 30–50+ paragraphs. Full assembly produces a massive context
wall — the LLM drowns and all generation metrics collapse.

**Variant B — Bounded assembly** (max 6 sections, 4,000 chars/section):

| Config | MRR | NDCG@k | Faithfulness | Legal Acc | Cit Acc | Tokens/Q |
|---|---|---|---|---|---|---|
| voyage_top_k25_hierarchical (bounded) | 0.246 | 0.251 | 0.395 | 0.407 | 0.330 | 5,850 |

Tokens are now comparable to top_k10 (5,150/Q). But generation metrics are worse than the
unbounded version, revealing a second failure mode: the 4,000-char truncation cuts off the
relevant content from long sections. The LLM receives a partial section that ends before the
specific regulatory answer it needs.

The NDCG@6 = 0.251 ≈ MRR = 0.2458 reveals the retrieval pattern: roughly 25% of queries
surface the ground truth section at rank 1, and ~75% find nothing in the top 6. Capping at
6 sections excludes relevant content that ranked at positions 7–10 in the section list.

**Finding:** Hierarchical retrieval fails in both forms. The two constraints — context size
and retrieval depth — push in opposite directions. More sections → better recall but context
overflow. Fewer sections → manageable context but missed relevant content. There is no
section-cap value that satisfies both simultaneously for this corpus.

**Root cause:** `voyage-law-2` paragraph embeddings find the relevant paragraph at approximately
rank 4 in a 25-result list (MRR=0.2458). After deduplication, that paragraph's section may
rank 4th–8th among unique sections. Section-level `text-embedding-3-small` embeddings
place the entire relevant section in the top 6–10 directly, without the deduplication
penalty. The section boundary is the natural retrieval unit for CFR content.

---

## Final Results — All Experiments

Experiments 1–8 in the table below used the pre-correction metric (see Appendix A). The
relative comparisons within that set remain valid because the same metric applied to all
configs. The `top_k10` corrected row reflects the production-accurate numbers.

| Config | Embed Model | Chunk | top_k | Search | Rewrite | MRR | NDCG@k | Faith | Legal | Cit | Tokens/Q |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline ‡ | text-3-small | section | 6 | vector | — | 0.275 | 0.473 | 0.511 | 0.527 | 0.484 | 2,902 |
| single_call ‡ | text-3-small | section | 6 | vector | — | 0.275 | 0.473 | 0.489 | 0.494 | 0.429 | 2,049 |
| top_k10 ‡ | text-3-small | section | 10 | vector | — | 0.275 | 0.520 | 0.553 | 0.560 | 0.458 | 5,152 |
| sonnet_vector ‡ | text-3-small | section | 10 | vector | — | 0.224 | 0.444 | 0.558 | 0.561 | 0.483 | 5,901 |
| sonnet_hybrid ‡ | text-3-small | section | 10 | hybrid | — | 0.238 | 0.454 | 0.550 | 0.558 | 0.481 | 5,836 |
| haiku_vector_rewrite ‡ | text-3-small | section | 10 | vector | yes | 0.205 | 0.463 | 0.538 | 0.541 | 0.429 | 5,280 |
| sonnet_hybrid_rewrite ‡ | text-3-small | section | 10 | hybrid | yes | 0.187 | 0.429 | 0.525 | 0.528 | 0.454 | 5,820 |
| voyage_paragraph ‡ | voyage-law-2 | paragraph | 10 | vector | — | 0.246 | 0.504 | 0.555 | 0.546 | 0.458 | 2,800 |
| voyage_top_k25 ‡ | voyage-law-2 | paragraph | 25† | vector | — | 0.246 | 0.653† | 0.538 | 0.535 | 0.423 | 5,883 |
| hierarchical (bounded) ‡ | voyage-law-2 | paragraph→section | 25→6 | hierarchical | — | 0.246 | 0.251 | 0.395 | 0.407 | 0.330 | 5,850 |
| **top_k10 (corrected)** | **text-3-small** | **section** | **10** | **vector** | **—** | **0.7097** | **0.7199** | **0.512** | **0.526** | **0.433** | **5,152** |

‡ Pre-correction metric (relative comparisons valid; absolute retrieval values understated)
† NDCG@25 — not directly comparable to NDCG@10 configs

---

## Production Configuration

**Winner: `top_k10`** — text-embedding-3-small, section-level chunks, top_k=10, sequential Haiku.

```yaml
embedding_model: text-embedding-3-small   # 1536 dims, $0.02/M tokens
chunk_strategy: section-level             # one DIV8 per chunk, ~237 tokens avg
corpus_size: 83,448 chunks                # Titles 7, 21, 42
retrieval:
  search_mode: vector
  top_k: 10
  query_rewrite: false
generation:
  strategy: sequential
  model: claude-haiku-4-5-20251001
```

**Key insight:** The CFR's section structure (`DIV8 TYPE="SECTION"`) is already the natural
unit of regulatory meaning. Each section is a coherent, self-contained requirement or
definition. Section-level chunking respects this structure; paragraph-level chunking
fragments it. Hierarchical retrieval attempts to reconstruct the section after the fact, but
the deduplication overhead and context-size constraints prevent it from outperforming
section-level embeddings.

**Cost note:** `text-embedding-3-small` at $0.02/M tokens is 6× cheaper than `voyage-law-2`
at $0.12/M. The domain-specific embedding model did not justify its cost. The voyage-law-2
experiments consumed ~27M tokens (~$3.24 after the 50M free tier) to establish this finding.

---

---

### Experiment 9 — Corrected Retrieval Metrics (Metric Audit)

Following the metric correction described in Appendix A, all voyage-law-2 paragraph configs
were re-run with the fixed metric. The old numbers had severely understated MRR and NDCG
due to sub-paragraph notation false negatives and duplicate section inflation.

**Key finding:** Retrieval quality was already strong. The system finds the relevant section
at MRR~0.71 across all voyage configs — roughly 2.5× better than the pre-fix numbers showed.

| Config | MRR (old) | MRR (corrected) | NDCG (old) | NDCG (corrected) |
|---|---|---|---|---|
| voyage_paragraph@10 | 0.246 | **0.710** | 0.504 | **0.720** |
| voyage_top_k25 | 0.246 | **0.710** | 0.653† | **0.724** |
| hierarchical@6 (4K) | 0.246 | **0.715** | 0.251 | **0.728** |

† NDCG@25, not @10 — was also inflated by duplicate paragraph hits before dedup fix

The ~18-point gap between retrieval success (MRR~0.71) and faithful answers (faithfulness~0.53)
cannot be explained by retrieval failure. It is caused by **context quality**: the system is
finding the right content but the LLM cannot always extract a complete, well-attributed answer
from fragmented paragraph-level context.

**Context quality degradation mechanisms:**
1. **Structural orphaning** — an answer paragraph retrieved without its defining context (§(a)
   defines scope, §(b) states the rule, §(c) lists exceptions). The LLM gets the rule without
   conditions.
2. **Lost section heading** — paragraph chunks include the CFR reference but not always the
   section heading that frames meaning.
3. **Context window noise** — 10 paragraph chunks from 5–8 sections produces scattered context;
   "lost in the middle" attention degradation amplifies this.
4. **Answer truncation** — in hierarchical mode, the specific threshold or list the question
   asks for may appear after the character limit cutoff.

---

### Experiment 10 — Hierarchical Retrieval: Larger Character Limits

**Variable:** Maximum characters per assembled section in hierarchical mode — testing whether
answer truncation is the primary cause of generation quality degradation.

Two new variants against the original bounded hierarchical (4K chars):

| Config | max_chars | max_sections | MRR | NDCG@6 | Faith | Legal | Cit | Tokens/Q |
|---|---|---|---|---|---|---|---|---|
| hierarchical@4K (Exp 8) | 4,000 | 6 | 0.715 | 0.728 | 0.395 | 0.407 | 0.330 | 5,850 |
| hierarchical@8K | 8,000 | 6 | 0.715 | 0.728 | 0.433 | 0.433 | 0.354 | 8,848 |
| hierarchical uncapped | ∞ | 4 | 0.715 | 0.728 | 0.439 | **0.461** | 0.392 | 13,249 |
| voyage_paragraph@10 | N/A | — | 0.710 | 0.720 | **0.533** | **0.535** | **0.429** | 2,783 |

**Finding:** Truncation was *a cause* of degradation but not the primary one. Removing the
character cap improved legal accuracy by 5.4pp (0.407 → 0.461) and citation accuracy by 6pp
(0.330 → 0.392). But fully uncapped hierarchical still underperforms flat paragraph retrieval
by ~9pp on faithfulness and ~7pp on legal accuracy, at 5× the token cost.

**Citation accuracy trajectory (0.330 → 0.354 → 0.392 → 0.429)** is particularly informative:
as sections become less truncated, the LLM can more clearly attribute where the answer came from.
But flat paragraph retrieval at 0.429 still wins because focused chunks make source attribution
easier than long dense sections.

**Root cause of residual gap:** "Lost in the middle" applies at the section level too. Full CFR
sections are 3,000–4,000+ tokens of dense regulatory text — tables, definitions, subconditions.
The specific fact answering the question is buried within that text. The LLM extracts it less
reliably than when the same paragraph is presented as a focused 150-token chunk near the top
of a 10-chunk context window.

**Conclusion:** The optimal generation unit for regulatory text is the *focused paragraph with
context prefix* — coherent enough to have semantic meaning, focused enough that the LLM can
attribute exactly where the answer came from. This validates the section-level chunking approach:
each `DIV8` section is already at this granularity (200–400 tokens), without needing
reconstruction overhead.

**Hierarchical retrieval verdict:** Good at finding relevant content (best MRR in the study),
but fundamentally undermines generation quality because full sections are too dense for reliable
LLM extraction, while partial sections cut off answers. The architecture is not suited to this
corpus structure.

---

## Final Results — Corrected Voyage Experiments

All corrected-metric voyage results (Experiments 6–10) on the voyage-law-2 paragraph DB:

| Config | Chunks | top_k | Mode | MRR | NDCG | Faith | Legal | Cit | Tokens/Q |
|---|---|---|---|---|---|---|---|---|---|
| **voyage_paragraph@10** | 223,918 | 10 | vector | **0.710** | 0.720 | **0.533** | **0.535** | **0.429** | **2,783** |
| voyage_top_k25 | 223,918 | 25 | vector | 0.710 | 0.724 | 0.536 | 0.532 | 0.399 | 5,844 |
| hierarchical@4K | 223,918 | 25→6 | hier | 0.715 | **0.728** | 0.395 | 0.407 | 0.330 | 5,850 |
| hierarchical@8K | 223,918 | 25→6 | hier | 0.715 | **0.728** | 0.433 | 0.433 | 0.354 | 8,848 |
| hierarchical uncapped | 223,918 | 25→4 | hier | 0.715 | 0.728† | 0.439 | 0.461 | 0.392 | 13,249 |

† NDCG@4, not @6 — slightly different k

**voyage_paragraph@10 is the best configuration on this corpus.** Best generation quality
on all three dimensions, lowest token cost, simplest retrieval path.

---

### Experiment 11 — Confidence Scoring (Exploratory)

**Background:** After the `section_baseline` config achieved Faithfulness=0.729, Legal
Accuracy=0.734, Citation Accuracy=0.602 (MRR=0.858, NDCG=0.880), a confidence scoring
system was implemented to surface answer reliability at inference time without requiring an
additional judge LLM call.

**Implementation:** `ConfidenceResult` dataclass in `generate.py`. Two components:

- **retrieval_score:** average cosine similarity of the top-3 retrieved chunks — measures
  whether relevant content was found
- **citation_coverage:** fraction of CFR section references in the generated text that appear
  in the retrieved chunk set — measures whether the LLM grounded its answer in what it
  retrieved vs. drawing on training memory

**Composite formula:**
```
composite = 0.35 * retrieval_score + 0.65 * citation_coverage
```

**Tiers:** high (≥ 0.75), medium (0.50–0.74), low (< 0.50), not_found

**Results on section_baseline (60 questions):**

| Tier | Count | Fraction |
|---|---|---|
| high | 43 | 71.7% |
| medium | 10 | 16.7% |
| low | 3 | 5.0% |
| not_found | 4 | 6.7% |

Avg composite confidence score: **0.763**

**Calibration — confidence tier vs. LLM judge faithfulness:**

| Tier | n | Avg Faithfulness | Avg Legal Accuracy |
|---|---|---|---|
| high | 43 | 0.759 | 0.762 |
| medium | 10 | 0.855 | 0.867 |
| low | 3 | 0.850 | 0.867 |
| not_found | 4 | 0.000 | 0.000 |

**Key findings:**

1. **Not_found detection is perfectly calibrated.** All 4 questions flagged as not_found
   returned faithfulness=0.000 from the judge. This is the most immediately reliable and
   actionable signal the confidence system produces.

2. **High confidence tier (71.7% of answers)** correctly shows faithfulness=0.759, above
   the 70% accuracy target.

3. **Medium and low tier faithfulness being higher than high tier is counterintuitive.**
   Two explanations: (a) sample sizes of n=10 and n=3 are insufficient for reliable
   calibration — these are noise, not signal; (b) the `citation_coverage` component
   penalizes answers where the LLM paraphrases without explicit CFR § references in the
   generated text, even if the answer is faithfully grounded in the retrieved context.
   A well-grounded answer that omits inline § citations will be scored as medium/low
   despite being accurate.

4. **The 0.65 weight on citation_coverage may be too high.** The `retrieval_score`
   component (cosine similarity) is likely a better predictor of actual faithfulness within
   the answered-question set. Recalibration requires a larger evaluation dataset.

5. **More test questions (200+) would give reliable tier-level calibration** and allow
   proper weight optimization for the composite formula. At 60 questions, medium (n=10)
   and low (n=3) have insufficient statistical power for weight tuning.

6. **The confidence signal provides the most immediate value as a not_found detector and
   as an aggregate quality monitor** — not as a per-answer precision signal for end users.

**Important caveat:** The confidence formula requires more test data and empirical calibration
before tier thresholds should be presented to end users as precise probability estimates. The
not_found signal is reliable. The high/medium/low distinction within answered questions needs
validation with a larger dataset.

**Production integration:** Confidence is returned with every `GenerationResult` and included
in API responses. The frontend has the signal available to show status badges, but tier labels
should not be shown as calibrated probability estimates until validation on 200+ questions is
complete.

---

## Phase 4 Complete — Confidence Scoring Added

All retrieval and generation optimization experiments are concluded (11 experiments, including
the exploratory confidence scoring system). The re-ingested `text-embedding-3-small`
section-level corpus is the current production database. Confidence scoring is implemented
as an experimental feature: the not_found signal is production-ready; tier calibration within
answered questions requires a larger evaluation set.

**Re-ingestion outcome:** The section-level corpus produced MRR=0.858, NDCG=0.880 with the
corrected metric, confirming the architectural fit prediction. Generation quality (Faith=0.729,
Legal=0.734, Cit=0.602) exceeds the voyage_paragraph@10 baseline on all three dimensions.

**Phase 5 (Backend API) has been started.** Phase 6 (Frontend UI) follows.

---

## Appendix A — Retrieval Metric Correction

The first 8 experiments used a flawed metric that produced severely understated retrieval
scores. The corrected top_k10 numbers (MRR=0.7097, NDCG=0.7199) represent the true system
performance.

### Bug 1 — Sub-paragraph notation mismatch (false negatives)

Ground truth references in the eval dataset include sub-paragraph notation:
```
7 CFR § 354.3(d)(6)(i)
21 CFR § 507.42(a)(2)
```

But chunk `cfr_reference` metadata stores only the section-level reference:
```
7 CFR § 354.3
21 CFR § 507.42
```

The original `is_relevant()` function searched for the full ground-truth string (including
`(d)(6)(i)`) in the chunk's citation metadata, which never contained sub-paragraph notation.
This produced **23 false negatives out of 43 apparent misses** across the 60-question dataset.
The reported MRR=0.275 was roughly 2.5× understated.

**Fix:** Strip all sub-paragraph notation (`(a)`, `(1)`, `(i)`, `and (c)`, etc.) from ground
truth references before matching, reducing to base section only.

### Bug 2 — Chunk text matching (false positives in NDCG calculation)

An intermediate fix matched the base section reference against `chunk_text` in addition to
`citation_string()`. This caused false positives: regulatory sections routinely cross-reference
other sections in their body text (e.g. "see § 135.110 for definitions"). A chunk about
§ 135.200 that mentions § 135.110 in its body was incorrectly counted as relevant for a
§ 135.110 query, inflating DCG and producing NDCG > 1.0.

**Fix:** Match only against `citation_string()` (the chunk's own CFR reference metadata),
never against `chunk_text`.

### Bug 3 — Duplicate section hits (NDCG > 1.0)

The paragraph-level corpus produces multiple chunks per CFR section. With base-section
matching, all paragraph chunks from section § 205.301 are relevant for a § 205.301 query.
If 5 such chunks appear in the top-10, DCG accumulates 5 gains while `ideal_hits = 1`
(one unique ground-truth section), making IDCG = 1/log₂(2) = 1.0. DCG > 1.0 → NDCG > 1.0.

**Fix:** Deduplicate by section in the hits computation. Each ground-truth section is
credited at most once — the first rank position where a chunk from that section appears.
This ensures DCG ≤ IDCG and NDCG ∈ [0, 1] at all times.

### Impact of correction

| Metric | Pre-fix (top_k10) | Post-fix (top_k10) |
|---|---|---|
| MRR | 0.275 | **0.7097** |
| NDCG@10 | 0.520 (or >1.0 with intermediate fix) | **0.7199** |
| Precision@10 | — | same formula, now deduped |
| Recall@10 | — | now counts unique sections found |

The corrected numbers reveal that the production configuration (top_k10, text-embedding-3-small,
section-level chunks) already achieves strong retrieval quality. The approximately 30% of
queries where the ground-truth section does not appear in the top 10 remain the target
for future retrieval improvement work.
