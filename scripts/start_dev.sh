#!/usr/bin/env bash
# scripts/start_dev.sh — Start backend (port 8002) and frontend (port 3002) for local dev.
# Usage: bash scripts/start_dev.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Government Regulation RAG — Development Server ==="
echo ""

# Backend
echo "[backend] Starting FastAPI on :8002..."
cd "${PROJECT_ROOT}"
source venv/bin/activate
uvicorn backend.main:app --reload --port 8002 &
BACKEND_PID=$!
echo "[backend] PID ${BACKEND_PID}"

# Frontend
if [ -d "${PROJECT_ROOT}/frontend" ]; then
    echo "[frontend] Starting Next.js on :3002..."
    cd "${PROJECT_ROOT}/frontend"
    npm run dev -- --port 3002 &
    FRONTEND_PID=$!
    echo "[frontend] PID ${FRONTEND_PID}"
fi

echo ""
echo "Backend:  http://localhost:8002"
echo "Frontend: http://localhost:3002"
echo "API docs: http://localhost:8002/docs"
echo ""
echo "Press Ctrl+C to stop all servers."

# Wait for Ctrl+C, then kill both
trap "kill ${BACKEND_PID} ${FRONTEND_PID:-} 2>/dev/null; exit 0" SIGINT SIGTERM
wait
