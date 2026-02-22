from fastapi import APIRouter
from pydantic import BaseModel
from settings import settings

router = APIRouter(prefix="/settings", tags=["settings"])

class NetworkToggle(BaseModel):
    enabled: bool

@router.get("/network-mode")
async def get_network_mode():
    return {"enabled": settings.get_network_enabled()}

@router.put("/network-mode")
async def set_network_mode(toggle: NetworkToggle):
    settings.set_network_enabled(toggle.enabled)
    return {"status": "success", "enabled": toggle.enabled}
