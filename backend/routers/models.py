import os
import httpx
from fastapi import APIRouter
from settings import settings

router = APIRouter(prefix="/models", tags=["models"])

def get_api_key():
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../api_key.txt"))
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    return ""

@router.get("")
async def list_models():
    # Base offline model
    models = [{
        "id": "qwen2.5-vl-72b-instruct", 
        "name": "Qwen 2.5 VL 72B", 
        "provider": "INTERNAL",
        "context_length": 128000,
        "pricing": {"prompt": "0", "completion": "0"}
    }]
    
    # Always fetch OpenRouter models if we have a key, regardless of the UI's offline toggle.
    # The offline toggle is meant to emulate an air-gapped system for the LLM's tools, not restrict the user from selecting OpenRouter models themselves.
    api_key = get_api_key()
    if api_key:
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("data", []):
                        models.append({
                            "id": m["id"],
                            "name": m.get("name", m["id"]),
                            "provider": "OPENROUTER",
                            "context_length": m.get("context_length", 0),
                            "pricing": m.get("pricing", {"prompt": "0", "completion": "0"})
                        })
        except Exception as e:
            print(f"Error fetching OpenRouter models: {e}")
                
    return models
