# LLM Agent Hub — Deployment Guide

## Overview
The application uses **Gradio** for the UI and **Python backend services** for LLM interaction. The entire app is a single Python process.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up API Key (for OpenRouter models)
Create `api_key.txt` in the project root with your OpenRouter API key:
```
sk-or-v1-YOUR_API_KEY_HERE
```

### 3. Launch the App
```bash
python app.py
```
The app will be available at **http://localhost:7860**

## Internal LLM Deployment (Air-gapped / On-premise)

### Using Docker (vLLM)
```bash
cd docker
docker-compose up -d
```

Make sure to update `docker-compose.yml` to point to your local model weights directory.

The internal model server runs on port **8000** and the Gradio app connects to it automatically when an internal model is selected.

### OpenShift Deployment
Use `docker/openshift-deployment.yaml` for deploying the vLLM server on OpenShift.

## Configuration
- **Offline Mode**: Toggle the "Offline Mode" checkbox in the sidebar to disable cloud models
- **Models**: Models are fetched dynamically from OpenRouter. The internal model (Qwen 2.5 VL 72B) is always available.
- **Modes**: Auto / Fast / Thinking / Pro — each adjusts temperature and system prompt behavior

## Architecture
```
app.py                      ← Gradio UI (entry point)
backend/
  database.py               ← SQLite database connection
  settings.py               ← Global settings (network toggle)
  models/
    db_models.py             ← Conversation table (SQLAlchemy)
    schemas.py               ← Pydantic schemas
  services/
    llm_router.py            ← Routes to internal vs OpenRouter
    openrouter.py            ← OpenRouter API streaming
    internal_llm.py           ← Local vLLM streaming
    models.py                ← Model list fetching
    history.py               ← Conversation CRUD
docker/
  Dockerfile                 ← vLLM container
  docker-compose.yml         ← Docker Compose for vLLM
  openshift-deployment.yaml  ← OpenShift manifests
```
