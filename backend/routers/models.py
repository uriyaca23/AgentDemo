import os
import re
import httpx
from fastapi import APIRouter
from settings import settings

router = APIRouter(prefix="/models", tags=["models"])


def _prettify_model_name(raw_id: str) -> str:
    """
    Convert ugly vLLM model paths into clean display names.
    
    Examples:
        '/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct' -> 'Qwen 2.5 0.5B Instruct'
        'Qwen/Qwen2.5-VL-72B-Instruct'                -> 'Qwen 2.5 VL 72B Instruct'
        'meta-llama/Llama-3-8B-Instruct'               -> 'Llama 3 8B Instruct'
        'openai/gpt-4o-mini'                           -> 'GPT 4o Mini'
    """
    name = raw_id

    # Strip common path prefixes from vLLM
    name = re.sub(r'^.*/model_cache/', '', name)
    name = re.sub(r'^.*/', '', name)  # Keep only the last path segment

    # Replace underscores with spaces (Qwen_Qwen2.5 -> Qwen Qwen2.5)
    name = name.replace('_', ' ')

    # Replace hyphens with spaces
    name = name.replace('-', ' ')

    # Remove duplicate vendor prefix (e.g. "Qwen Qwen2.5" -> "Qwen2.5")
    parts = name.split()
    if len(parts) >= 2 and parts[1].lower().startswith(parts[0].lower()):
        parts = parts[1:]
    name = ' '.join(parts)

    # Add space before version numbers (Qwen2.5 -> Qwen 2.5)
    name = re.sub(r'([A-Za-z])(\d)', r'\1 \2', name)

    # Title case single-word parts that are all lower
    final_parts = []
    for part in name.split():
        if part.islower() and len(part) > 2:
            final_parts.append(part.capitalize())
        else:
            final_parts.append(part)
    
    return ' '.join(final_parts)


def get_api_key():
    if settings.is_internal_llm():
        return "internal-emulator-key"
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../api_key.txt"))
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    return ""

@router.get("")
async def list_models():
    models = []
    
    # Determine provider label based on active settings
    is_internal = settings.is_internal_llm()
    provider_label = "INTERNAL" if is_internal else "OPENROUTER"
    
    # Fetch models from the configured LLM endpoint
    api_key = get_api_key()
    if api_key:
        try:
            # Robust Authorization header
            auth_val = api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"
            headers = {"Authorization": auth_val}
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.get_llm_base_url()}/models",
                    headers=headers,
                    timeout=30.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("data", []):
                        # Calculate cost_per_m as the old version did
                        pricing = m.get("pricing") or {}
                        # If pricing is a string (unexpected but safer)
                        if isinstance(pricing, str): pricing = {}
                        
                        prompt_price = float(pricing.get("prompt", 0) or 0)
                        cost_per_m = prompt_price * 1000000
                        
                        # Capability Detection
                        capabilities = {
                            "thinking": "none",
                            "tools": False,
                            "multimodal": False
                        }
                        
                        m_id_low = m["id"].lower()
                        m_name_low = (m.get("name") or "").lower()
                        
                        # 1. Thinking / Reasoning Detection
                        # Native reasoning models
                        if any(x in m_id_low for x in ["deepseek-r1", "openai/o1", "openai/o3", "reasoning"]):
                            capabilities["thinking"] = "native"
                        # Models that can reliably follow thinking instructions (simulated)
                        elif any(x in m_id_low for x in ["instruct", "chat", "qwen", "llama-3", "gpt-4", "claude-3", "gemini-2"]) \
                             or any(x in m_name_low for x in ["instruct", "chat", "qwen", "llama", "gpt", "claude", "gemini"]):
                            capabilities["thinking"] = "simulated"
                            
                        # 2. Tools Support (based on OpenRouter meta or name)
                        # OpenRouter often provides 'tool_use' in some meta, but not always in /models
                        # We'll use a conservative name-based check + common knowledge
                        if any(x in m_id_low for x in ["gpt-4", "gpt-3.5", "claude-3", "gemini", "llama-3", "mistral", "mixtral", "qwen-2.5-72b"]):
                            capabilities["tools"] = True
                            
                        # 3. Multimodal Support
                        if any(x in m_id_low for x in ["-vl", "-vision", "gpt-4o", "claude-3", "gemini", "pixtral"]):
                            capabilities["multimodal"] = True

                        # Preserve all original fields but override specific UI ones
                        model_entry = {
                            **m,
                            "name": _prettify_model_name(m.get("name") or m.get("id", "Unknown")),
                            "provider": provider_label,
                            "cost_per_m": cost_per_m,
                            "intelligence": 8, # Fallback intelligence
                            "speed": 8,        # Fallback speed
                            "capabilities": capabilities
                        }
                        
                        # Special handling for intelligence/speed based on context or name
                        if "gpt-4" in m["id"] or "claude-3" in m["id"]:
                            model_entry["intelligence"] = 10
                        elif "mini" in m["id"] or "haiku" in m["id"] or "flash" in m["id"]:
                            model_entry["speed"] = 10
                            model_entry["intelligence"] = 7
                            
                        models.append(model_entry)
                else:
                    print(f"[Models] LLM API returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[Models] Error fetching models from {settings.get_llm_base_url()}: {e}")
    
    # If no models were fetched, add a fallback — label matches the active provider
    if not models:
        if is_internal:
            models.append({
                "id": "qwen2.5-vl-72b-instruct", 
                "name": "Qwen 2.5 VL 72B Instruct", 
                "provider": "INTERNAL",
                "description": "Powerful self-hosted multimodal model optimized for air-gapped workloads.",
                "cost_per_m": 0.0,
                "context_length": 128000,
                "intelligence": 9,
                "speed": 7,
                "capabilities": {
                    "thinking": "simulated",
                    "tools": True,
                    "multimodal": True
                }
            })
        else:
            # OpenRouter fallback
            for fb in [
                {"id": "openai/gpt-4o-mini", "name": "GPT 4o Mini", "cost": 0.15},
                {"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku", "cost": 0.25},
                {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "cost": 0.1},
                {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "cost": 0.3},
                {"id": "qwen/qwen-2.5-72b-instruct", "name": "Qwen 2.5 72B Instruct", "cost": 0.4},
            ]:
                models.append({
                    "id": fb["id"],
                    "name": fb["name"],
                    "provider": "OPENROUTER",
                    "description": "Reliable fallback model tier.",
                    "cost_per_m": fb["cost"],
                    "context_length": 128000,
                    "intelligence": 8,
                    "speed": 9,
                    "capabilities": {
                        "thinking": "simulated",
                        "tools": True,
                        "multimodal": "mini" not in fb["id"] and "flash" not in fb["id"] # Heuristic
                    }
                })
                
    return models
