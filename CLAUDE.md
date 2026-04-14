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

## Ingestion (starter corpus: Titles 7, 21, 42)
```bash
source venv/bin/activate
python src/ingest.py --title 7     # Title 7: Agriculture
python src/ingest.py --title 21    # Title 21: Food and Drugs
python src/ingest.py --title 42    # Title 42: Public Health
python src/ingest.py --all-starter # All three starter titles
```

## Evaluation
```bash
python eval/src/evaluate.py --config eval/configs/baseline.yaml
python eval/run_all.py --phase 2   # Chunk size sweep
python eval/run_all.py --phase 5   # Top-k sweep
```

## Phase checklist
- [ ] Phase 0: Repository Setup & Component Reuse
- [ ] Phase 1: Corpus Ingestion & Parsing (eCFR API)
- [ ] Phase 2: Retrieval Engine & Metadata Filtering
- [ ] Phase 3: Three-Output Generation
- [ ] Phase 4: Evaluation & Quality Assurance
- [ ] Phase 5: Backend API
- [ ] Phase 6: Frontend UI
- [ ] Phase 7: Deployment (regs.bradhinkel.com, DigitalOcean)
- [ ] Phase 8: Corpus Freshness & Versioned Replacement
- [ ] Phase 9: Corpus Expansion (all 50 CFR titles)
