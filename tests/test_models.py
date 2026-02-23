import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from main import app
from backend.routers import models as models_router

@pytest.mark.asyncio
@patch("routers.models.settings.get_network_enabled")
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_list_offline_mode(mock_httpx_class, mock_get_key, mock_network):
    """When offline, OpenRouter models should STILL be available for selection."""
    mock_network.return_value = False
    mock_get_key.return_value = "fake_key"
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku"}
        ]
    }
    
    class AsyncClientMock:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs): return mock_response
        
    mock_httpx_class.return_value = AsyncClientMock()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/models")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 3 # 1 internal + 2 external
        assert data[0]["id"] == "qwen2.5-vl-72b-instruct"
        assert data[0]["provider"] == "INTERNAL"
        providers = [m["provider"] for m in data]
        assert providers.count("OPENROUTER") == 2

@pytest.mark.asyncio
@patch("routers.models.settings.get_network_enabled")
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_list_online_mode_success(mock_httpx_class, mock_get_key, mock_network):
    """When online with a key, external models should be appended to the list."""
    mock_network.return_value = True
    mock_get_key.return_value = "fake_key"
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku"},
            {"id": "random/model"} 
        ]
    }
    
    # Setup async context manager mock
    class AsyncClientMock:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs): return mock_response
        
    mock_httpx_class.return_value = AsyncClientMock()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/models")
        assert res.status_code == 200
        data = res.json()
        
        # Internal model + 3 external models 
        assert len(data) == 4
        providers = [m["provider"] for m in data]
        assert "INTERNAL" in providers
        assert providers.count("OPENROUTER") == 3
        assert any(m["id"] == "openai/gpt-4o-mini" for m in data)

@pytest.mark.asyncio
@patch("routers.models.settings.get_network_enabled")
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_list_online_mode_api_failure(mock_httpx_class, mock_get_key, mock_network):
    """If the external API fails (e.g. 401 or network error), it should gracefully return just the internal model."""
    mock_network.return_value = True
    mock_get_key.return_value = "bad_key"
    
    # Setup exception
    class AsyncClientMock:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs): raise Exception("Network Timeout")
        
    mock_httpx_class.return_value = AsyncClientMock()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/models")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["provider"] == "INTERNAL"
