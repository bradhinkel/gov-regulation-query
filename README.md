# Government Regulation Query

A retrieval-augmented generation (RAG) system over the U.S. Code of Federal Regulations. Ask a natural-language question about federal rules and get three grounded outputs:

1. **Plain-English explanation** — accessible, jargon-free
2. **Legal/Regulatory language** — domain-voice synthesis with verbatim quotes
3. **CFR Citations** — precise Title / Part / Section references (e.g., `7 CFR § 205.301`)

The corpus covers 8 major CFR titles — agriculture, food and drugs, public health, energy, aviation, labor, environment, and transportation (Titles 7, 10, 14, 21, 29, 40, 42, 49) — totaling ~253,000 regulatory sections ingested directly from the free [eCFR API](https://www.ecfr.gov/developers).

Beyond basic Q&A, the system covers the regulatory **time axis** and audits its own quality:

- **Temporal queries** — "what changed?" questions diff the current text against archived versions of the same sections.
- **Corpus freshness** — a weekly incremental sync detects amended sections via the eCFR versioner and swaps them in atomically; every citation carries a "current as of" date.
- **Inline grounding verification** — every answer gets a deterministic confidence score; answers in the ambiguous band are escalated to an independent LLM judge that checks each claim against the retrieved text before delivery (validated at 100% catch rate on seeded ungrounded answers).
- **Self-maintaining evaluation library** — 200+ stratified questions (definitions, numeric standards, procedures, penalties, enumerated lists, adversarial, out-of-corpus negatives) anchored to CFR sections; the library retires/re-references questions automatically as the corpus changes, and scheduled runs publish a longitudinal quality trend to `/health`.
- **Improvement loop** — user thumbs-down, judge-flagged, and security-downgraded answers enter a triage queue; triaged failures are promoted into the eval library as regression cases and tracked to closure.

## Links

- **Live system:** [regs.bradhinkel.com](https://regs.bradhinkel.com)
- **Project background & case study:** [bradhinkel.com](https://bradhinkel.com) → *Projects*

## Stack

- **Backend:** Python 3.12, FastAPI, asyncpg / psycopg3
- **Vector store:** PostgreSQL 16 + pgvector
- **Embeddings:** OpenAI `text-embedding-3-small`
- **Generation:** Anthropic `claude-haiku-4-5`
- **Grounding judge / eval:** Anthropic `claude-sonnet-4-6`
- **Frontend:** Next.js 14, TypeScript, Tailwind CSS
- **Ingest:** lxml + httpx against the eCFR API

## Deploy it yourself (local)

### 1. Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 16 with the `pgvector` and `uuid-ossp` extensions available
- API keys for [OpenAI](https://platform.openai.com/) and [Anthropic](https://console.anthropic.com/)

### 2. Clone and install

```bash
git clone https://github.com/<your-fork>/gov-regulation-query.git
cd gov-regulation-query

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### 3. Configure environment

Copy the example file and fill in your keys:

```bash
cp .env.example .env
# edit .env: set OPENAI_API_KEY, ANTHROPIC_API_KEY, and DATABASE_URL password
```

### 4. Create the database

```bash
sudo -u postgres psql < src/db/schema.sql
```

This creates the `regulation_rag` database, the `regulation_app` user, and the schema (chunks table, vector index, status enum for versioned swaps).

Then apply the feature migrations (query history confidence, sync state, the eval library, and the inline-quality columns):

```bash
sudo -u postgres psql regulation_rag < scripts/migrate_queries_confidence.sql
sudo -u postgres psql regulation_rag < scripts/migrate_sync_tables.sql
sudo -u postgres psql regulation_rag < scripts/migrate_eval_library.sql
sudo -u postgres psql regulation_rag < scripts/migrate_part_b.sql
```

(Use the stdin-redirect form as shown — the postgres OS user typically can't read files inside your home directory.)

### 5. Ingest regulations

Start with a single title, or ingest the full 8-title corpus:

```bash
source venv/bin/activate
python src/ingest.py --title 7                          # Agriculture
python src/ingest.py --titles 7 10 14 21 29 40 42 49    # full corpus
```

Oversized titles (e.g. 40/EPA) whose full-title eCFR XML times out are fetched part-by-part automatically. Full 8-title ingest takes a few hours, dominated by eCFR fetch time; embedding (OpenAI `text-embedding-3-small`) is fast.

### 6. Run the app

Backend (port 8002):

```bash
source venv/bin/activate
uvicorn backend.main:app --reload --port 8002
```

Frontend (port 3002), in a separate terminal:

```bash
cd frontend
npm run dev -- --port 3002
```

Open http://localhost:3002.

### Optional: run the evaluation harness

```bash
# Classic config-driven harness
python eval/src/evaluate.py --config eval/configs/baseline.yaml

# Self-maintaining eval library (Phase 10)
python eval/src/library.py seed              # author the stratified library (one-off LLM cost)
python eval/src/library.py status            # stratum coverage + stable-core size
python eval/src/run_library_eval.py --scope core   # judged run over the stable core
python eval/src/eval_grounding_gate.py --n 20      # hallucination-gate catch rate
python eval/src/triage.py list                     # poor-result triage queue
```

See `eval/configs/` for tunable retrieval and generation configurations, and `docs/confidence_calibration_findings.md` for the confidence-calibration study.

## Requirements & licenses

### Project

Released under the **MIT License**. See `LICENSE` (add one in your fork if redistributing).

### Python dependencies (`requirements.txt`)

| Package | Version | License |
|---|---|---|
| fastapi | 0.115.0 | MIT |
| uvicorn[standard] | 0.30.6 | BSD-3-Clause |
| python-dotenv | 1.0.1 | BSD-3-Clause |
| pydantic | 2.8.2 | MIT |
| psycopg[binary] | 3.2.1 | LGPL-3.0 |
| asyncpg | 0.29.0 | Apache-2.0 |
| pgvector (Python client) | 0.3.2 | MIT |
| openai | 1.51.0 | Apache-2.0 |
| anthropic | 0.34.2 | MIT |
| voyageai | 0.3.2 | MIT |
| httpx | 0.27.2 | BSD-3-Clause |
| lxml | 5.3.0 | BSD-3-Clause |
| rich | 13.8.1 | MIT |
| pyyaml | 6.0.2 | MIT |
| numpy | 1.26.4 | BSD-3-Clause |

### Frontend dependencies (`frontend/package.json`)

| Package | Version | License |
|---|---|---|
| next | 14.2.5 | MIT |
| react / react-dom | ^18 | MIT |
| typescript | ^5 | Apache-2.0 |
| tailwindcss | ^3.4.1 | MIT |
| postcss | ^8 | MIT |
| eslint / eslint-config-next | ^8 / 14.2.5 | MIT |

### System dependencies

| Component | License |
|---|---|
| PostgreSQL 16 | PostgreSQL License (permissive, BSD-like) |
| pgvector extension | PostgreSQL License |

### Data

The corpus itself — the U.S. Code of Federal Regulations — is a work of the U.S. federal government and is in the **public domain**. Ingestion goes through the free, unauthenticated [eCFR API](https://www.ecfr.gov/developers). Please respect their rate limits.
