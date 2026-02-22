from fastapi import APIRouter
import httpx
from models.schemas import ModelMetadata

router = APIRouter(prefix="/models", tags=["models"])

MOCK_FALLBACK = [
    {
        "id": "qwen/qwen-2.5-72b-instruct",
        "name": "Qwen 2.5 72B",
        "provider": "openrouter",
        "description": "Powerful external version of Qwen via OpenRouter.",
        "cost_per_m": 0.35,
        "context_length": 32768,
        "intelligence": 9,
        "speed": 8
    },
    {
        "id": "openai/gpt-4o",
        "name": "GPT-4o (Vision)",
        "provider": "openrouter",
        "description": "Flagship multi-modal OpenAI model",
        "cost_per_m": 5.0,
        "context_length": 128000,
        "intelligence": 10,
        "speed": 8
    },
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "provider": "openrouter",
        "description": "High intelligence model for complex tasks.",
        "cost_per_m": 3.0,
        "context_length": 200000,
        "intelligence": 10,
        "speed": 6
    }
]

cached_models = []

@router.get("")
async def list_models():
    global cached_models
    
    internal_models = [{
        "id": "qwen2.5-vl-72b-instruct",
        "name": "Qwen 2.5 VL 72B",
        "provider": "internal",
        "description": "Powerful self-hosted multimodal model optimized for air-gapped workloads.",
        "cost_per_m": 0.0,
        "context_length": 32768,
        "intelligence": 9,
        "speed": 7
    }]

    openrouter_models = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://openrouter.ai/api/v1/models", timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("data", []):
                    openrouter_models.append({
                        "id": m["id"],
                        "name": m.get("name") or m["id"],
                        "provider": "openrouter",
                        "description": m.get("description", "Dynamic OpenRouter Model"),
                        "cost_per_m": float(m.get("pricing", {}).get("prompt", 0) or 0) * 1000000,
                        "context_length": m.get("context_length", 8192),
                        "intelligence": 8,
                        "speed": 8
                    })
                # Sort them alphabetically for better UI
                openrouter_models.sort(key=lambda x: x["name"])
                cached_models = openrouter_models
    except Exception as e:
        print(f"Failed to fetch models: {e}")

    if not openrouter_models:
        openrouter_models = cached_models if cached_models else MOCK_FALLBACK

    return internal_models + openrouter_models
