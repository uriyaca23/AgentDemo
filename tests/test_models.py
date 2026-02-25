import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from main import app

@pytest.mark.asyncio
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_list_with_external_models(mock_httpx_class, mock_get_key):
    """When external models are fetched, they should be returned (no hardcoded fallback)."""
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
        assert len(data) == 2  # Only the fetched models
        assert any(m["id"] == "openai/gpt-4o-mini" for m in data)
        assert any(m["id"] == "anthropic/claude-3-haiku" for m in data)

@pytest.mark.asyncio
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_list_api_failure_shows_fallback(mock_httpx_class, mock_get_key):
    """If the external API fails, it should return fallback models."""
    mock_get_key.return_value = "bad_key"
    
    class AsyncClientMock:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, *args, **kwargs): raise Exception("Network Timeout")
        
    mock_httpx_class.return_value = AsyncClientMock()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/models")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1  # At least one fallback model

@pytest.mark.asyncio
@patch("routers.models.settings.is_internal_llm")
@patch("routers.models.settings.get_llm_base_url")
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_list_internal_llm_provider_label(mock_httpx_class, mock_get_key, mock_url, mock_internal):
    """When using internal LLM, fetched models should be labeled INTERNAL not OPENROUTER."""
    mock_internal.return_value = True
    mock_url.return_value = "http://emulator:8000/api/v1"
    mock_get_key.return_value = "internal-emulator-key"
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "Qwen/Qwen2.5-VL-72B-Instruct-AWQ", "name": "Qwen 2.5 VL 72B"}
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
        assert len(data) == 1  # Only the fetched model (no duplicate fallback)
        assert data[0]["provider"] == "INTERNAL"

@pytest.mark.asyncio
@patch("routers.models.get_api_key")
async def test_models_no_api_key_shows_fallback(mock_get_key):
    """With no API key, should return fallback models."""
    mock_get_key.return_value = ""
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/models")
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1  # At least one fallback model

@pytest.mark.asyncio
@patch("routers.models.get_api_key")
@patch("routers.models.httpx.AsyncClient")
async def test_models_names_are_prettified(mock_httpx_class, mock_get_key):
    """Model names from emulator should be prettified, not raw paths."""
    mock_get_key.return_value = "fake_key"
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"id": "/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct", "name": "/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct"}
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
        # The name should be prettified
        assert "model_cache" not in data[0]["name"]
        assert "/app" not in data[0]["name"]
        # But the ID should be preserved for API calls
        assert data[0]["id"] == "/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct"
