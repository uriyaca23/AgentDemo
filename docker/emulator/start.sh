#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# OpenRouter Emulator — Entrypoint Script
# Starts vLLM backend on port 5000, then the emulator API on 8000.
# ─────────────────────────────────────────────────────────────────

set -e

MODEL_PATH="${MODEL_PATH:-/app/model}"
TENSOR_PARALLEL="${TENSOR_PARALLEL_SIZE:-3}"
QUANTIZATION="${QUANTIZATION:-awq}"
VLLM_PORT=5000
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"

echo "═══════════════════════════════════════════════════════════"
echo "  OpenRouter Emulator Starting"
echo "  Model path:      $MODEL_PATH"
echo "  Tensor parallel:  $TENSOR_PARALLEL"
echo "  Quantization:     $QUANTIZATION"
echo "  GPU Memory Util:  $GPU_MEMORY_UTILIZATION"
echo "═══════════════════════════════════════════════════════════"

# ── Build vLLM launch command ────────────────────────────────────
VLLM_CMD="python3 -m vllm.entrypoints.openai.api_server \
    --model $MODEL_PATH \
    --tensor-parallel-size $TENSOR_PARALLEL \
    --port $VLLM_PORT \
    --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
    --trust-remote-code"

# Add quantization only if set (skip for non-quantized models like testing with 0.5B)
if [ "$QUANTIZATION" != "none" ]; then
    VLLM_CMD="$VLLM_CMD --quantization $QUANTIZATION"
fi

# Add max-model-len if specified (useful for testing with limited GPU memory)
if [ -n "$MAX_MODEL_LEN" ]; then
    VLLM_CMD="$VLLM_CMD --max-model-len $MAX_MODEL_LEN"
fi

echo "Starting vLLM: $VLLM_CMD"
$VLLM_CMD &
VLLM_PID=$!

# ── Wait for vLLM to become healthy ─────────────────────────────
echo "Waiting for vLLM to start on port $VLLM_PORT..."
MAX_WAIT=300  # 5 minutes max (large models take time to load)
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s "http://localhost:$VLLM_PORT/v1/models" > /dev/null 2>&1; then
        echo "✓ vLLM is healthy after ${WAITED}s"
        break
    fi
    
    # Check if vLLM process died
    if ! kill -0 $VLLM_PID 2>/dev/null; then
        echo "✗ vLLM process died unexpectedly!"
        exit 1
    fi
    
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "✗ vLLM failed to start within ${MAX_WAIT}s"
    kill $VLLM_PID 2>/dev/null
    exit 1
fi

# ── Start the emulator API ───────────────────────────────────────
export VLLM_BASE_URL="http://localhost:$VLLM_PORT/v1"
export EMULATOR_PORT=8000

echo "Starting OpenRouter Emulator API on port $EMULATOR_PORT..."
cd /app/emulator
python3 emulator_app.py &
EMULATOR_PID=$!

# ── Wait for emulator health ────────────────────────────────────
sleep 2
if curl -s "http://localhost:$EMULATOR_PORT/" > /dev/null 2>&1; then
    echo "✓ Emulator is healthy"
else
    echo "⚠ Emulator may still be starting..."
fi

echo "═══════════════════════════════════════════════════════════"
echo "  ✓ All services running"
echo "    vLLM:     http://localhost:$VLLM_PORT"
echo "    Emulator: http://localhost:$EMULATOR_PORT"
echo "═══════════════════════════════════════════════════════════"

# ── Keep container alive — wait for either process to exit ───────
wait -n $VLLM_PID $EMULATOR_PID
EXIT_CODE=$?
echo "A process exited with code $EXIT_CODE — shutting down..."
kill $VLLM_PID $EMULATOR_PID 2>/dev/null
exit $EXIT_CODE
