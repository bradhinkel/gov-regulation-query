#!/usr/bin/env bash
# scripts/setup_db.sh — Create the regulation_rag database and run schema migrations.
# Run once on a fresh install: sudo bash scripts/setup_db.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_FILE="${PROJECT_ROOT}/src/db/schema.sql"

echo "=== Government Regulation RAG — Database Setup ==="
echo "Schema: ${SCHEMA_FILE}"
echo ""

if ! command -v psql &>/dev/null; then
    echo "[error] psql not found. Install PostgreSQL 16 first."
    exit 1
fi

echo "[1/2] Running schema.sql as postgres user..."
sudo -u postgres psql < "${SCHEMA_FILE}"

echo ""
echo "[2/2] Verifying pgvector extension..."
sudo -u postgres psql -d regulation_rag -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"

echo ""
echo "Setup complete. Connect with:"
echo "  psql postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag"
