# Deployment Guide

## Architecture Options

### Option 1: OpenRouter (External, for Development/Testing)
Point the backend at OpenRouter's public API (default behavior).

```
LLM_BASE_URL=https://openrouter.ai/api/v1  (default, no env var needed)
```

### Option 2: Internal Emulator (Air-gapped, for Organization)
Deploy the OpenRouter Emulator Docker image which wraps vLLM with an OpenRouter-compatible API layer.

```
LLM_BASE_URL=http://emulator-host:8000/api/v1
```

---

## Air-gapped Organizational Deployment

### 1. Model Weights Preparation
Download the `Qwen/Qwen2.5-VL-72B-Instruct-AWQ` model and transfer it to the target offline server.
```bash
# On a machine with internet access:
huggingface-cli download Qwen/Qwen2.5-VL-72B-Instruct-AWQ --local-dir ./Qwen2.5-VL-72B-Instruct-AWQ
# Then copy to the target server
```

### 2. Docker Compose (Standalone)
```bash
cd docker
MODEL_WEIGHTS_PATH=/path/to/Qwen2.5-VL-72B-Instruct-AWQ docker-compose up --build -d
```

The emulator exposes port 8000. Set the backend to use it:
```
LLM_BASE_URL=http://localhost:8000/api/v1
```

### 3. OpenShift Deployment (Interactive)
Use the interactive deployment script which prompts for all org-specific parameters:
```powershell
cd docker
.\deploy-openshift.ps1
```

The script prompts for:
- OpenShift namespace/project
- Container registry URL
- GPU count (default: 3)
- Quantization method (default: awq)
- GPU memory utilization
- Max model length
- PVC name for model weights
- Optional host path

After deployment, the emulator service is available at:
```
http://openrouter-emulator-service.<namespace>.svc:8000/api/v1
```

### 4. Backend Configuration
Set this environment variable before starting the backend:
```bash
LLM_BASE_URL=http://openrouter-emulator-service.<namespace>.svc:8000/api/v1
```

When `LLM_BASE_URL` points to the emulator:
- API key validation is skipped (no real auth needed internally)
- Models are labeled as `INTERNAL` in the model list
- All existing features (streaming, tool use, modes) work identically

---

## Local Testing (Docker Desktop)

For testing with a small model on a consumer GPU:

```bash
cd docker
docker build -t openrouter-emulator-test -f Dockerfile.test .
docker run -d --gpus all -p 8000:8000 --name emulator-test openrouter-emulator-test
```

This downloads `Qwen/Qwen2.5-0.5B-Instruct` automatically and runs it with:
- 1 GPU, no quantization
- max_model_len=2048
- 80% GPU memory utilization

Run compatibility tests:
```bash
python -m pytest tests/test_emulator_compat.py -v -m docker
```

---

## Emulator API Endpoints

The emulator provides these OpenRouter-compatible endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/auth/key` | Auth stub (always returns 200) |
| `GET /api/v1/models` | Lists loaded vLLM models in OpenRouter format |
| `POST /api/v1/chat/completions` | Chat completions (streaming + non-streaming) |
| `GET /` | Health check |
