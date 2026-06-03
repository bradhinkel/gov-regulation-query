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
      - [ ] 9.2: weekly change-detection sync job + 20% threshold alert
      - [ ] 9.4: temporal "what changed?" query handler (current + archived)
      - [ ] 9.6: sync logging + /health freshness; 9.7: freshness/temporal eval
- [ ] Phase 9.1: Eval Expansion (200+ questions) & Confidence Reweighting
