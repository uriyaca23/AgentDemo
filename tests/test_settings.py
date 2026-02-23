import os
import sys
import pytest
import httpx
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_network_mode_toggle():
    """Verify that we can toggle the global offline mode."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/settings/network-mode")
        assert res.status_code == 200
        initial_state = res.json()["enabled"]
        
        # Toggle
        res2 = await client.put("/settings/network-mode", json={"enabled": not initial_state})
        assert res2.status_code == 200
        assert res2.json()["enabled"] == (not initial_state)

        # Restore
        await client.put("/settings/network-mode", json={"enabled": initial_state})

@pytest.mark.asyncio
async def test_api_key_status_flow():
    """Verify the API Key status checking returns correct states."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Depending on local disk state, it will be true/false. But we verify the schema.
        res = await client.get("/settings/api-key-status")
        assert res.status_code == 200
        data = res.json()
        assert "is_locked" in data
        assert "valid" in data

@pytest.mark.asyncio
async def test_unlock_key_wrong_password():
    """Test that providing the wrong password fails safely with 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/settings/unlock-key", json={"password": "wrong_password"})
        assert res.status_code == 401
        assert "Failed to unlock API key" in res.json()["detail"]

@pytest.mark.asyncio
async def test_unlock_key_correct_password():
    """Test that providing the correct password extracts the key."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/settings/unlock-key", json={"password": "Quantom2321999"})
        assert res.status_code == 200
        assert res.json()["status"] == "success"
