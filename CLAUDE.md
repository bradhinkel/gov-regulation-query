# Government Regulation Query — Claude Code Session Guide

## Project overview
RAG system over U.S. federal regulations (eCFR). Answers natural language questions
about federal regulations with three outputs per query:
  1. Plain English explanation — accessible, jargon-free
  2. Legal/Regulatory language — authoritative, domain-voice synthesis with verbatim quotes
  3. CFR Citations — precise Title/Part/Section references (e.g., 7 CFR § 205.301)

**This is the third milestone in a portfolio progression:**
- D&D Item Generator (completed) — proof of concept
- Sword Coast RAG (completed) — architectural prototype, three-output pattern
- Government Regulation Query (this project) — production-ready, specialized domain

Architecture inherits directly from Sword Coast RAG (`~/rag-query-engine`).

## Working directory
`/home/bradhinkel/gov-regulation-query/`

Sword Coast reference: `~/rag-query-engine/` (do not modify — archived)

## Stack
- Python 3.12 / FastAPI / asyncpg / psycopg3
- PostgreSQL 16 + pgvector (vector store, same instance as Sword Coast dev)
- OpenAI `text-embedding-3-small` (embeddings)
- Anthropic `claude-haiku-4-5-20251001` (generation + eval judge)
- Next.js 14 / TypeScript / Tailwind CSS (frontend)
- lxml / httpx (eCFR XML parsing + API fetch)

## Key architecture decisions
- **eCFR API as corpus source** — free, structured XML, no auth required
- **Regulatory-aware chunking at § boundaries** — each DIV8 (SECTION) is a natural chunk
- **status + version_id on every chunk** — enables atomic swap for weekly refresh (Phase 8)
- **ALL retrieval queries include `AND status = 'active'`** — enforced in query.py, never per-call-site
- **ENABLE_VERBATIM_QUOTES=true** — federal regulations are public domain; verbatim citation is the value proposition
- **LLM_CALL_STRATEGY=sequential** — two calls: plain English first, then legal language with verbatim quotes

## Database
- Dev database: `regulation_rag` (local PostgreSQL, same instance as sword_coast_rag)
- DB user: `regulation_app` / password in .env
- Schema: src/db/schema.sql (includes status ENUM, version_id, full CFR hierarchy metadata)

## Running locally
```bash
# Backend (from project root)
source venv/bin/activate
uvicorn backend.main:app --reload --port 8002

# Frontend
cd frontend && npm run dev -- --port 3002
```

## Database setup
```bash
sudo -u postgres psql < src/db/schema.sql
```

## Ingestion (corpus: 8 CFR titles — 7, 10, 14, 21, 29, 40, 42, 49 ≈ 253K sections)
```bash
source venv/bin/activate
python src/ingest.py --title 7              # Agriculture (USDA)
python src/ingest.py --titles 7 21 42      # multiple titles in one run
# Full 8-title corpus:
python src/ingest.py --titles 7 10 14 21 29 40 42 49
# Agriculture(7) Energy(10) Aeronautics(14) Food&Drugs(21) Labor(29)
# Environment(40) Public Health(42) Transportation(49)
```
Oversized titles (e.g. 40/EPA, 94K sections) whose full-title eCFR XML times out
are fetched part-by-part automatically (see _fetch_title_parts in xml_parser.py).

## Evaluation
```bash
python eval/src/evaluate.py --config eval/configs/baseline.yaml
python eval/run_all.py --phase 2   # Chunk size sweep
python eval/run_all.py --phase 5   # Top-k sweep

# Phase 10 Part A — DB-backed self-maintaining eval library:
python eval/src/library.py seed              # build library to quotas (~160 Qs)
python eval/src/library.py status            # stratum coverage + stable-core size
python eval/src/library.py refresh           # post-sync retire/re-reference/top-up
python eval/src/run_library_eval.py --scope core   # weekly trend run
python eval/src/run_library_eval.py --scope full   # monthly full run
```

## Phase checklist
- [x] Phase 0: Repository Setup & Component Reuse
- [x] Phase 1: Corpus Ingestion & Parsing (eCFR API)
- [x] Phase 2: Retrieval Engine & Metadata Filtering
- [x] Phase 3: Three-Output Generation
- [x] Phase 4: Evaluation & Quality Assurance
- [x] Phase 5: Backend API
- [x] Phase 6: Frontend UI
- [x] Phase 7: Deployment — LIVE at regs.bradhinkel.com (DigitalOcean droplet
      137.184.234.166, /opt/regs; systemd regs-backend :8002 + regs-frontend :3002,
      nginx + Certbot TLS, deploy via rsync since /opt/regs is not a git checkout)
- [x] Phase 8.5: Security Hardening (input validation, rate limiting, intent
      classifier, prompt hardening, output validation) — deployed
- [x] Phase 8.6: Corpus Expansion to 8 CFR titles (7,10,14,21,29,40,42,49 ≈
      253K sections) + HNSW index. Built on laptop, shipped to droplet via
      pg_dump → chunks_new staging → indexes → atomic rename swap. Droplet
      resized to 8GB. Live at regs.bradhinkel.com.
- [~] Phase 9: Corpus Freshness & Versioned Replacement
      - [x] 9.0: fixed stale corpus (titles 10/14/29/40/49 were 2017-2021 due to
            the _get_latest_date bug); re-ingested current 2026 editions via
            staged-ingest (ingest.py --target-status staged) + atomic swap
            (scripts/swap_version.py). All 8 titles now current; 265,595 chunks.
      - [x] 9.5: citations show "current as of [date]" (effective_date in payload)
      - [x] 9.2/9.3: incremental change-detection (versioner issue_date[gte]) +
            per-section staged swap (src/sync.py); 20% threshold alert; sync_state
            watermark + sync_runs audit. Reconciled drifted titles 7/21/42.
      - [x] 9.4: temporal "what changed?" handler — is_temporal_query intent,
            fetch_section_versions (active+archived), generate_temporal diff
            summary; falls back to a normal answer when no archived history.
      - [x] 9.6: weekly systemd timer (deploy/regs-sync.*) + /health freshness.
      - [x] 9.7: freshness/temporal eval (eval/src/eval_freshness_temporal.py):
            intent 100%, staleness 0%, temporal coverage 75%, faithfulness ~0.72
            (strong on prose amendments; large enumerated list sections are the
            weak spot — generation model is configurable via TEMPORAL_MODEL).
- [x] Phase 9.1: Eval expansion (200 Qs, 8 titles) & confidence calibration.
      Added retrieval_concentration + grid search (eval/src/optimize_confidence.py).
      Finding (docs/confidence_calibration_findings.md): no inference-time signal
      predicts judge faithfulness (best ρ≈0.04); root causes — (1) the Haiku judge
      was unreliable (0.28 agreement w/ Sonnet; scored correct answers 0.3), and
      (2) even w/ a Sonnet judge, answered-question quality is uniformly high
      (~0.90) so there's no gradient to predict. Decisions: concentration kept as
      a diagnostic at weight 0 (it's negatively correlated); no spurious
      reweighting; eval judge upgraded to Sonnet (JUDGE_MODEL). not_found remains
      the validated confidence primitive.
- [ ] Phase 9.1: Eval Expansion (200+ questions) & Confidence Reweighting
- [x] Phase 10: Frontend redesign — "Official Record" (trust-forward UI). Cosmetic
      only; backend/retrieval/routing unchanged. Per design/ handoff bundle.
      - Three self-hosted typefaces via next/font/local (frontend/app/fonts/):
        Spectral (display+prose), Public Sans (UI), IBM Plex Mono (citation refs).
        Self-hosted to avoid flaky build-time Google Fonts fetches under WSL2.
      - Dark default + full light theme via data-theme; tokens in app/globals.css.
      - New components (app/components/): Masthead, HomeView, ResultView,
        CitationsRail, Prose, Loader, StateCard, AboutModal, Field, Icons. Replaced
        QueryForm/StatusBanner/ResponsePanel/CitationList/PrintButton.
      - app/lib/parseAnswer.ts parses backend markdown answers into a block model and
        lifts inline `"quote" (CFR cite)` into gold "Verbatim statute" blocks (legal
        register). NOTE: depends on the generate.py output format — see memory
        frontend-answer-parser-coupling.
      - Trust trio at top (Grounded→scroll/pulse rail · Current-as-of · qualitative
        confidence, % hidden by default); citations grouped by title, link to ecfr.gov.
      - app/lib/cfr.ts: full 8-title name map (fixes "Title N" bug), ecfr URL builder,
        formatAgency (ALL-CAPS eCFR agency → "Agency · Department").
      - Provenance footer + printable PDF add dynamic "corpus updated as of <date>"
        (from /sources latest_date). Site favicon app/icon.svg (BH mark recolored).
      - Deployed to droplet via rsync app/ → build → restart regs-frontend. Prod API
        URL is /api (frontend/.env.production.local), nginx proxies /api/ → :8002.
        Live at regs.bradhinkel.com.
- [x] Phase 10 (Revised) Part A: unified grounding judge + self-maintaining eval
      library (docs/Phase 10 (Revised)*.docx supersedes the original draft).
      - src/judge.py: ONE judge for offline eval + (Part B) inline escalation.
        JUDGE_MODEL (Sonnet) rubric: grounding 1–5, completeness 1–5,
        correctness 0–1 vs reference (offline only), justification. Never raises;
        caller decides fail-open/closed.
      - scripts/migrate_eval_library.sql: eval_questions (anchored to
        cfr_reference + effective_date; status active|retired; times_refreshed>0
        or origin!='generated' ⇒ out of stable core), eval_runs, eval_results.
      - eval/src/library.py seed|refresh|status. Strata per title: definition,
        numeric_standard, procedure, penalty, enumerated_list (Phase 9.7 weak
        spot), adversarial (variance source Phase 9.1 lacked) + global negatives
        (out-of-corpus, must yield not_found). Stratum SQL predicates are
        section-level aggregates (chunks are ~1.5K-char splits — row-level
        length/count predicates never match). refresh: retire on removed
        sections, regenerate ground truth on amended ones (question survives,
        leaves core), top-up to quota. Questions must be self-contained (no
        "this section" deixis — retrieval can't resolve it).
      - eval/src/run_library_eval.py --scope core|full: production pipeline →
        judge; composite = 0.4·correctness + 0.4·grounding + 0.2·completeness;
        negatives score 1.0 iff not_found; EVAL_TOKEN_BUDGET cap (default 3M,
        exit 2 + status aborted_cost_cap, partial results kept). Persists
        eval_runs/eval_results; reports grounding_std (Part B calibration
        precondition).
      - /health now has an "eval" block: last run + stable-core trend delta
        (db_service.get_eval_health). regs-sync.service appends library refresh
        + weekly core run ('-' prefixed); deploy/regs-eval-full.{service,timer}
        runs the full library monthly on the 1st.
      - COMPLETE (2026-07-27): full seed at scale 1.0 on laptop AND droplet
        (160 active Qs, 159 stable core, all 8 titles × 6 strata + 16 negatives).
        First full runs: local composite 0.888 (grounding_std 0.092), droplet
        0.849. Droplet deployed: migration applied, judge/library rsynced,
        regs-eval-full.timer enabled (monthly, 1st), regs-sync weekly core run
        active, /health eval block live. Cost baseline: full 160-Q run ≈ 1.42M
        in / 123K out tokens (Haiku gen + Sonnet judge) ≈ $3–4 per run.
      - NEXT (Part B, steps 2–3 of docx): inline quality via selective judge
        escalation + quality payload + poor-result capture/triage/promotion.
        Calibration precondition check first: per-stratum grounding_std
        (adversarial/enumerated_list) before re-fitting confidence weights.
