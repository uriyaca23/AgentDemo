import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

import pytest
from httpx import AsyncClient, ASGITransport
from main import app

@pytest.mark.asyncio
async def test_read_root():
    """Verify that the FastAPI root endpoint works and routes are mounted"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.json() == {"status": "Backend V2 is running", "mounted": "/data"}

@pytest.mark.asyncio
async def test_chat_conversations_route_exists():
    """Verify that the chat router is correctly wired and DB connects"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # We don't have conversations yet, so it should return 200 []
        response = await client.get("/chat/conversations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_models_route_exists():
    """Verify the models router returns the internal model by default"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/models")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert data[0]["provider"] == "INTERNAL"
