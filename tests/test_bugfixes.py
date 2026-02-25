"""Tests for the 3 bug fixes: chat model auto-detection, OpenRouter model list, and provider labels."""
import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from main import app
from settings import settings


# ═══════════════════════════════════════════════════════════════════
# Bug 1: Chat model auto-detection for emulator
# ═══════════════════════════════════════════════════════════════════

class TestChatModelAutoDetect:
    """Tests that chat requests use the emulator's actual model, not the UI-selected model."""

    @pytest.mark.asyncio
    async def test_resolve_emulator_model_caching(self):
        """The emulator model resolver should cache results."""
        from services.openrouter import _resolve_emulator_model, invalidate_emulator_model_cache
        
        invalidate_emulator_model_cache()  # Clear cache
        
        with patch("services.openrouter.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": [{"id": "/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct"}]
            }
            
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client
            
            with patch("services.openrouter.settings") as mock_settings:
                mock_settings.get_llm_base_url.return_value = "http://emulator:8000/api/v1"
                
                # First call should hit the API
                result1 = await _resolve_emulator_model("fallback")
                assert result1 == "/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct"
                
                # Second call should use cache (no new API calls)
                result2 = await _resolve_emulator_model("fallback")
                assert result2 == result1
                assert mock_client.get.call_count == 1  # Only called once
        
        invalidate_emulator_model_cache()  # Clean up

    @pytest.mark.asyncio
    async def test_resolve_emulator_model_fallback_on_error(self):
        """If the emulator is unreachable, should return the fallback model."""
        from services.openrouter import _resolve_emulator_model, invalidate_emulator_model_cache
        
        invalidate_emulator_model_cache()
        
        with patch("services.openrouter.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client
            
            with patch("services.openrouter.settings") as mock_settings:
                mock_settings.get_llm_base_url.return_value = "http://emulator:8000/api/v1"
                
                result = await _resolve_emulator_model("my-fallback-model")
                assert result == "my-fallback-model"
        
        invalidate_emulator_model_cache()

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_state(self):
        """invalidate_emulator_model_cache should clear the cached model."""
        from services.openrouter import _resolve_emulator_model, invalidate_emulator_model_cache, _emulator_model_cache
        import services.openrouter as openrouter_module
        
        invalidate_emulator_model_cache()
        assert openrouter_module._emulator_model_cache is None


# ═══════════════════════════════════════════════════════════════════
# Bug 2: OpenRouter model list should not be empty
# ═══════════════════════════════════════════════════════════════════

class TestOpenRouterModelList:
    """Tests that switching to OpenRouter always shows models."""

    @pytest.mark.asyncio
    @patch("routers.models.settings.is_internal_llm")
    @patch("routers.models.settings.get_llm_base_url")
    @patch("routers.models.settings.get_active_provider")
    @patch("routers.models.get_api_key")
    @patch("routers.models.httpx.AsyncClient")
    async def test_openrouter_models_fetched_successfully(
        self, mock_httpx_class, mock_get_key, mock_provider, mock_url, mock_internal
    ):
        """When OpenRouter is active and returns models, they should all be labeled OPENROUTER."""
        mock_internal.return_value = False
        mock_url.return_value = "https://openrouter.ai/api/v1"
        mock_provider.return_value = "openrouter"
        mock_get_key.return_value = "real-api-key"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
                {"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku"},
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
            assert len(data) == 2
            for m in data:
                assert m["provider"] == "OPENROUTER"

    @pytest.mark.asyncio
    @patch("routers.models.settings.is_internal_llm")
    @patch("routers.models.settings.get_llm_base_url")
    @patch("routers.models.settings.get_active_provider")
    @patch("routers.models.get_api_key")
    @patch("routers.models.httpx.AsyncClient")
    async def test_openrouter_fallback_when_fetch_fails(
        self, mock_httpx_class, mock_get_key, mock_provider, mock_url, mock_internal
    ):
        """When OpenRouter fetch fails, fallback should show OPENROUTER models, NOT INTERNAL."""
        mock_internal.return_value = False
        mock_url.return_value = "https://openrouter.ai/api/v1"
        mock_provider.return_value = "openrouter"
        mock_get_key.return_value = "real-api-key"
        
        class AsyncClientMock:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs): raise Exception("Network error")
        
        mock_httpx_class.return_value = AsyncClientMock()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/models")
            assert res.status_code == 200
            data = res.json()
            assert len(data) > 0
            # ALL models should be labeled OPENROUTER, not INTERNAL
            for m in data:
                assert m["provider"] == "OPENROUTER", f"Expected OPENROUTER but got {m['provider']} for {m['id']}"

    @pytest.mark.asyncio
    @patch("routers.models.settings.is_internal_llm")
    @patch("routers.models.settings.get_llm_base_url")
    @patch("routers.models.settings.get_active_provider")
    @patch("routers.models.get_api_key")
    @patch("routers.models.httpx.AsyncClient")
    async def test_openrouter_fallback_includes_popular_models(
        self, mock_httpx_class, mock_get_key, mock_provider, mock_url, mock_internal
    ):
        """OpenRouter fallback should include well-known models the user can select."""
        mock_internal.return_value = False
        mock_url.return_value = "https://openrouter.ai/api/v1"
        mock_provider.return_value = "openrouter"
        mock_get_key.return_value = "real-api-key"
        
        class AsyncClientMock:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs): raise Exception("Timeout")
        
        mock_httpx_class.return_value = AsyncClientMock()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/models")
            data = res.json()
            ids = [m["id"] for m in data]
            assert "openai/gpt-4o-mini" in ids
            assert "anthropic/claude-3.5-haiku" in ids


# ═══════════════════════════════════════════════════════════════════
# Bug 3: Provider labels must always match active provider
# ═══════════════════════════════════════════════════════════════════

class TestProviderLabels:
    """Tests that the provider label is always correct."""

    @pytest.mark.asyncio
    @patch("routers.models.settings.is_internal_llm")
    @patch("routers.models.settings.get_active_provider")
    @patch("routers.models.get_api_key")
    @patch("routers.models.httpx.AsyncClient")
    async def test_emulator_models_labeled_internal(
        self, mock_httpx_class, mock_get_key, mock_provider, mock_internal
    ):
        """When emulator is active, all models should say INTERNAL."""
        mock_internal.return_value = True
        mock_provider.return_value = "emulator"
        mock_get_key.return_value = "internal-key"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "Qwen/Qwen2.5-0.5B-Instruct", "name": "Qwen 2.5 0.5B"}]
        }
        
        class AsyncClientMock:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs): return mock_response
        
        mock_httpx_class.return_value = AsyncClientMock()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/models")
            data = res.json()
            for m in data:
                assert m["provider"] == "INTERNAL"

    @pytest.mark.asyncio
    @patch("routers.models.settings.is_internal_llm")
    @patch("routers.models.settings.get_active_provider")
    @patch("routers.models.get_api_key")
    @patch("routers.models.httpx.AsyncClient")
    async def test_no_internal_label_in_openrouter_mode(
        self, mock_httpx_class, mock_get_key, mock_provider, mock_internal
    ):
        """When OpenRouter is active, no model should ever be labeled INTERNAL."""
        mock_internal.return_value = False
        mock_provider.return_value = "openrouter"
        mock_get_key.return_value = "real-key"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
                {"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku"},
            ]
        }
        
        class AsyncClientMock:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, *args, **kwargs): return mock_response
        
        mock_httpx_class.return_value = AsyncClientMock()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/models")
            data = res.json()
            for m in data:
                assert m["provider"] != "INTERNAL", f"Model {m['id']} should not be labeled INTERNAL in OpenRouter mode"
