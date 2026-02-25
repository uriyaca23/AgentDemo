import os
import pyzipper
from fastapi import APIRouter, HTTPException
from models.schemas import NetworkToggle, UnlockRequest, LlmProviderToggle
from settings import settings

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("/network-mode")
async def get_network_mode():
    return {"enabled": settings.get_network_enabled()}

@router.put("/network-mode")
async def set_network_mode(toggle: NetworkToggle):
    settings.set_network_enabled(toggle.enabled)
    return {"status": "success", "enabled": toggle.enabled}

import httpx

@router.get("/api-key-status")
async def get_api_key_status():
    # For internal emulator, no real API key is needed
    if settings.is_internal_llm():
        return {"is_locked": False, "valid": True}
    
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../api_key.txt"))
    if os.path.exists(key_path) and os.path.getsize(key_path) > 0:
        with open(key_path, "r") as f:
            key = f.read().strip()
        # Verify it against the LLM API to ensure it wasn't revoked
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{settings.get_llm_base_url()}/auth/key",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=5.0
                )
                if res.status_code == 200:
                    return {"is_locked": False, "valid": True}
        except Exception:
            pass
            
    return {"is_locked": True, "valid": False}

@router.post("/unlock-key")
async def unlock_api_key(req: UnlockRequest):
    zip_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../locked_secrets/api_key.zip"))
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="API Key zip file not found in locked_secrets.")
        
    try:
        with pyzipper.AESZipFile(zip_path) as z:
            z.pwd = req.password.encode('utf-8')
            z.extractall(out_dir)
        return {"status": "success", "message": "API key unlocked successfully."}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to unlock API key. Invalid password? ({str(e)})")

@router.get("/llm-provider")
async def get_llm_provider():
    """Returns the currently active LLM provider."""
    return {
        "provider": settings.get_active_provider(),
        "url": settings.get_llm_base_url()
    }

@router.put("/llm-provider")
async def set_llm_provider(toggle: LlmProviderToggle):
    """Switch between emulator and OpenRouter at runtime."""
    from services.openrouter import invalidate_emulator_model_cache
    
    if toggle.provider == "emulator":
        settings.set_llm_base_url(settings.get_emulator_url())
    elif toggle.provider == "openrouter":
        settings.set_llm_base_url(settings.get_openrouter_url())
    else:
        raise HTTPException(status_code=400, detail="Invalid provider. Use 'emulator' or 'openrouter'.")
    
    # Clear the cached emulator model ID when switching providers
    invalidate_emulator_model_cache()
    
    return {
        "status": "success",
        "provider": settings.get_active_provider(),
        "url": settings.get_llm_base_url()
    }

