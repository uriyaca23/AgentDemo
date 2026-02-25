#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# start-app.sh — Self-contained app entrypoint
# Starts the FastAPI backend on port 8001 and Next.js frontend on port 3000
# ─────────────────────────────────────────────────────────────────

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  LLM Chatbot UI — Starting"
echo "═══════════════════════════════════════════════════════════"

# ── Start Backend ────────────────────────────────────────────────
echo "Starting backend on port 8001..."
cd /app/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 &
BACKEND_PID=$!

# Wait for backend to start
echo "Waiting for backend to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8001/ > /dev/null 2>&1; then
        echo "✓ Backend is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "✗ Backend failed to start in 30s!"
        exit 1
    fi
    sleep 1
done

# ── Start Frontend ───────────────────────────────────────────────
echo "Starting frontend on port 3000..."
cd /app/frontend-standalone
PORT=3000 HOSTNAME=0.0.0.0 node server.js &
FRONTEND_PID=$!

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ App is running!"
echo "    Frontend: http://localhost:3000"
echo "    Backend:  http://localhost:8001"
echo "═══════════════════════════════════════════════════════════"

# ── Handle shutdown ──────────────────────────────────────────────
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGTERM SIGINT

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
