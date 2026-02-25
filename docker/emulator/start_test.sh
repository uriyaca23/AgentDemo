#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# OpenRouter Emulator — Test Entrypoint
# Downloads the model from HuggingFace (if not cached) and starts
# both vLLM + emulator. Designed for local testing on consumer GPUs.
# ─────────────────────────────────────────────────────────────────

set -e

MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-0.5B-Instruct}"
MODEL_PATH="/app/model_cache/${MODEL_NAME//\//_}"
TENSOR_PARALLEL="${TENSOR_PARALLEL_SIZE:-1}"
QUANTIZATION="${QUANTIZATION:-none}"
VLLM_PORT=5000
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.80}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"

echo "═══════════════════════════════════════════════════════════"
echo "  OpenRouter Emulator — TEST MODE"
echo "  Model:            $MODEL_NAME"
echo "  Tensor parallel:  $TENSOR_PARALLEL"
echo "  Quantization:     $QUANTIZATION"
echo "  Max model len:    $MAX_MODEL_LEN"
echo "═══════════════════════════════════════════════════════════"

# ── Download model if not already cached ─────────────────────────
if [ ! -d "$MODEL_PATH" ]; then
    echo "Downloading model $MODEL_NAME..."
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('$MODEL_NAME', local_dir='$MODEL_PATH')
"
    echo "✓ Model downloaded to $MODEL_PATH"
else
    echo "✓ Model already cached at $MODEL_PATH"
fi

# ── Start vLLM ───────────────────────────────────────────────────
VLLM_CMD="python3 -m vllm.entrypoints.openai.api_server \
    --model $MODEL_PATH \
    --tensor-parallel-size $TENSOR_PARALLEL \
    --port $VLLM_PORT \
    --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
    --max-model-len $MAX_MODEL_LEN \
    --dtype auto \
    --trust-remote-code"

if [ "$QUANTIZATION" != "none" ]; then
    VLLM_CMD="$VLLM_CMD --quantization $QUANTIZATION"
fi

echo "Starting vLLM: $VLLM_CMD"
$VLLM_CMD &
VLLM_PID=$!

# ── Wait for vLLM health ─────────────────────────────────────────
echo "Waiting for vLLM to start..."
MAX_WAIT=180
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s "http://localhost:$VLLM_PORT/v1/models" > /dev/null 2>&1; then
        echo "✓ vLLM is healthy after ${WAITED}s"
        break
    fi
    if ! kill -0 $VLLM_PID 2>/dev/null; then
        echo "✗ vLLM process died!"
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

# ── Start emulator ───────────────────────────────────────────────
export VLLM_BASE_URL="http://localhost:$VLLM_PORT/v1"
export EMULATOR_PORT=8000

echo "Starting OpenRouter Emulator API on port $EMULATOR_PORT..."
cd /app/emulator
python3 emulator_app.py &
EMULATOR_PID=$!

sleep 2
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ TEST MODE — All services running"
echo "    vLLM:     http://localhost:$VLLM_PORT"
echo "    Emulator: http://localhost:$EMULATOR_PORT"
echo "═══════════════════════════════════════════════════════════"

wait -n $VLLM_PID $EMULATOR_PID
EXIT_CODE=$?
kill $VLLM_PID $EMULATOR_PID 2>/dev/null
exit $EXIT_CODE
