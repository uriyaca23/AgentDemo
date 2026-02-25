"""Tests for the LLM provider toggle endpoints and model name prettification."""
import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from main import app
from routers.models import _prettify_model_name
from settings import settings


# ═══════════════════════════════════════════════════════════════════
# Model Name Prettification Tests
# ═══════════════════════════════════════════════════════════════════

class TestPrettifyModelName:
    """Tests for the _prettify_model_name helper."""

    def test_vllm_cache_path(self):
        """Strip /app/model_cache/ prefix and format nicely."""
        result = _prettify_model_name("/app/model_cache/Qwen_Qwen2.5-0.5B-Instruct")
        assert "model_cache" not in result
        assert "app" not in result.lower().split()
        # Should contain key parts
        assert "Qwen" in result
        assert "Instruct" in result

    def test_slash_separated_id(self):
        """Handle org/model format like 'Qwen/Qwen2.5-VL-72B-Instruct'."""
        result = _prettify_model_name("Qwen/Qwen2.5-VL-72B-Instruct")
        assert "/" not in result
        assert "VL" in result
        assert "72B" in result

    def test_openai_model(self):
        """Handle OpenAI-style names."""
        result = _prettify_model_name("openai/gpt-4o-mini")
        assert "/" not in result
        # Should be readable
        assert len(result) > 3

    def test_llama_model(self):
        """Handle Llama-style names."""
        result = _prettify_model_name("meta-llama/Llama-3-8B-Instruct")
        assert "Llama" in result
        assert "8B" in result

    def test_simple_name_passthrough(self):
        """Simple names should pass through cleanly."""
        result = _prettify_model_name("Qwen 2.5 VL 72B")
        assert result == "Qwen 2.5 VL 72B"

    def test_no_ugly_underscores(self):
        """Underscores should be converted to spaces."""
        result = _prettify_model_name("Qwen_Qwen2.5-0.5B-Instruct")
        assert "_" not in result

    def test_root_model_cache(self):
        """Handle /root/model_cache/ prefix."""
        result = _prettify_model_name("/root/model_cache/mistral_Mistral-7B-Instruct-v0.3")
        assert "root" not in result.lower().split()
        assert "model_cache" not in result


# ═══════════════════════════════════════════════════════════════════
# Provider Toggle Endpoint Tests
# ═══════════════════════════════════════════════════════════════════

class TestProviderToggle:
    """Tests for GET/PUT /settings/llm-provider."""

    @pytest.mark.asyncio
    async def test_get_initial_provider(self):
        """GET /settings/llm-provider should return current provider."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/settings/llm-provider")
            assert res.status_code == 200
            data = res.json()
            assert "provider" in data
            assert "url" in data
            assert data["provider"] in ("emulator", "openrouter")

    @pytest.mark.asyncio
    async def test_toggle_to_openrouter(self):
        """PUT with provider='openrouter' should switch to OpenRouter URL."""
        original_url = settings.get_llm_base_url()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put("/settings/llm-provider", json={"provider": "openrouter"})
                assert res.status_code == 200
                data = res.json()
                assert data["provider"] == "openrouter"
                assert "openrouter.ai" in data["url"]
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_toggle_to_emulator(self):
        """PUT with provider='emulator' should switch to emulator URL."""
        original_url = settings.get_llm_base_url()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.put("/settings/llm-provider", json={"provider": "emulator"})
                assert res.status_code == 200
                data = res.json()
                assert data["provider"] == "emulator"
                assert "openrouter.ai" not in data["url"]
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_toggle_roundtrip(self):
        """Toggle emulator → openrouter → emulator should restore original state."""
        original_url = settings.get_llm_base_url()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Switch to OpenRouter
                await client.put("/settings/llm-provider", json={"provider": "openrouter"})
                res1 = await client.get("/settings/llm-provider")
                assert res1.json()["provider"] == "openrouter"

                # Switch back to emulator
                await client.put("/settings/llm-provider", json={"provider": "emulator"})
                res2 = await client.get("/settings/llm-provider")
                assert res2.json()["provider"] == "emulator"
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_invalid_provider(self):
        """Invalid provider name should return 400."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put("/settings/llm-provider", json={"provider": "invalid"})
            assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_models_refresh_after_toggle(self):
        """After toggling provider, /models should still return valid data."""
        original_url = settings.get_llm_base_url()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Toggle to openrouter
                await client.put("/settings/llm-provider", json={"provider": "openrouter"})
                res = await client.get("/models")
                assert res.status_code == 200
                models = res.json()
                assert isinstance(models, list)
                assert len(models) >= 1  # At least the fallback
        finally:
            settings.set_llm_base_url(original_url)
