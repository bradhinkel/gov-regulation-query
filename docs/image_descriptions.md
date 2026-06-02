# Case Study Image Descriptions

Companion to `Government_Regulation_Query_Case_Study.md`. Contains prompts and specs
for each image referenced (or to be referenced) in the case study.

---

## 1. Architecture Diagram — eraser.io prompt

**Suggested placement:** after the "The System in Brief" section, before "The Evaluation Framework".

**Diagram type:** cloud architecture / system diagram
**Style:** clean, left-to-right data flow, grouped into logical tiers
**Target tool:** eraser.io (use the "Generate Diagram" AI prompt field, or paste into a `cloud-architecture-diagram` doc)

### Prompt to paste into eraser.io

```
Create a cloud architecture diagram for a production Retrieval-Augmented Generation (RAG)
system over U.S. federal regulations. Layout: left-to-right, grouped into four tiers —
Ingestion (offline, batch), Data Layer, Runtime Request Path, and Client. Use clear
directional arrows with labels describing the payload on each edge. Title the diagram
"Federal Regulation RAG — Production Architecture".

Tier 1 — Ingestion (offline batch, shown with dashed borders to indicate non-runtime):
- External source: "eCFR XML API" (government public API, no auth)
- Python service: "Ingest Pipeline (src/ingest.py)" — fetches Titles 7, 21, 42 per title
- Python service: "XML Parser (lxml)" — parses DIV1 through DIV8 hierarchy,
  normalizes each DIV8 (SECTION) into one chunk with metadata
  (title, part, subpart, section number, heading, agency, CFR reference)
- External API: "OpenAI Embeddings API" — model text-embedding-3-small, 1536 dims
- Flow: eCFR XML API → Ingest Pipeline → XML Parser → OpenAI Embeddings API →
  writes to Postgres (shown as arrow into Data Layer)
- Annotation on the ingest arrow: "85,351 sections, status=active, version_id"

Tier 2 — Data Layer:
- Database: "PostgreSQL 16 + pgvector" — cosine similarity index, 796 MB on disk,
  hosted on a DigitalOcean 2 vCPU / 4GB droplet
- Note on the DB: every chunk has status ENUM (active | staged | archived)
  and version_id, enabling atomic version-swap refresh

Tier 3 — Runtime Request Path (this is the hot path for user queries):
- API: "FastAPI Backend (uvicorn + asyncpg)" — exposes POST /query with
  Server-Sent Events streaming
- Component inside the backend: "Retrieval" — pure vector cosine search,
  top_k=10, WHERE status='active' filter enforced at query layer
- External API: "OpenAI Embeddings API" (same as ingest, used to embed the user query)
- External API: "Anthropic Messages API — Claude Haiku 4.5" — called twice per query,
  sequential strategy:
    Call 1: generates plain-English answer
    Call 2: generates legal-language answer with verbatim quotes,
            conditioned on retrieved context + Call 1 output
- Component inside the backend: "Confidence Scorer" — computes
  0.35 × retrieval_score + 0.65 × citation_coverage, tiers into
  high / medium / low / not_found (no extra LLM call)
- SSE event stream out of the backend labeled with three events in order:
  "retrieving → generating → result"

Tier 4 — Client + Edge:
- Reverse proxy: "nginx" with "Let's Encrypt TLS" and "HSTS header"
- Process manager: "systemd" (wraps FastAPI + Next.js units on the droplet)
- Frontend: "Next.js 14 + Tailwind (SSR)" — single query form with three
  tabbed outputs (Plain English | Legal Language | CFR Citations) and
  a confidence tier badge
- End user: "Browser — regs.bradhinkel.com"

Runtime flow (draw as a numbered path):
1. Browser → nginx (HTTPS) → FastAPI /query
2. FastAPI → OpenAI Embeddings API (embed query)
3. FastAPI → PostgreSQL + pgvector (vector search, top_k=10, status='active')
4. FastAPI → Anthropic API (Call 1: plain English)
5. FastAPI → Anthropic API (Call 2: legal language + verbatim quotes)
6. FastAPI → Confidence Scorer (inline, no external call)
7. FastAPI → Browser (SSE: retrieving, generating, result)

Styling guidance:
- Group Ingestion tier in a dashed box labeled "Offline / Batch"
- Group Data Layer, Runtime, and Edge in a solid box labeled
  "DigitalOcean Droplet (2 vCPU / 4GB)"
- External APIs (OpenAI, Anthropic, eCFR) shown outside the droplet box
- Use the standard icons for PostgreSQL, nginx, OpenAI, Anthropic if available;
  otherwise clean labeled rectangles
- Color: muted, professional palette — no neon. Keep labels readable.
```

### If eraser.io's AI prompt misinterprets anything

Most common issue: it may try to put the Ingestion pipeline *inline* with the runtime
path. Reinforce by adding a line at the top of the prompt: **"The Ingestion tier runs
offline and writes to Postgres ahead of time. It is NOT called during a user query.
Draw it in a separate dashed container."**

Second most common: it may collapse the two Anthropic calls into one. Reinforce:
**"Show the two Anthropic API calls as two separate arrows labeled Call 1 and Call 2,
sequential not parallel."**
