import os
import pyzipper
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from settings import settings

router = APIRouter(prefix="/settings", tags=["settings"])

class NetworkToggle(BaseModel):
    enabled: bool

class UnlockRequest(BaseModel):
    password: str

@router.get("/network-mode")
async def get_network_mode():
    return {"enabled": settings.get_network_enabled()}

@router.put("/network-mode")
async def set_network_mode(toggle: NetworkToggle):
    settings.set_network_enabled(toggle.enabled)
    return {"status": "success", "enabled": toggle.enabled}

@router.get("/api-key-status")
async def get_api_key_status():
    key_path = os.path.join(os.path.dirname(__file__), "../../api_key.txt")
    if os.path.exists(key_path) and os.path.getsize(key_path) > 0:
        return {"is_locked": False}
    return {"is_locked": True}

@router.post("/unlock-key")
async def unlock_api_key(req: UnlockRequest):
    zip_path = os.path.join(os.path.dirname(__file__), "../../locked_secrets/api_key.zip")
    out_dir = os.path.join(os.path.dirname(__file__), "../../")
    
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="API Key zip file not found in locked_secrets.")
        
    try:
        with pyzipper.AESZipFile(zip_path) as z:
            z.pwd = req.password.encode('utf-8')
            z.extractall(out_dir)
        return {"status": "success", "message": "API key unlocked successfully."}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Failed to unlock API key. Invalid password? ({str(e)})")
