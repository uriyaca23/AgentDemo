"""Tests for background conversation title generation."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from services.openrouter import generate_title_background


class TestTitleGeneration:
    """Tests for generate_title_background()."""

    @pytest.mark.asyncio
    @patch("services.openrouter.settings")
    @patch("services.openrouter.httpx.AsyncClient")
    async def test_title_generation_success(self, mock_client_class, mock_settings):
        """Successful title generation should update the conversation."""
        mock_settings.is_internal_llm.return_value = False
        mock_settings.get_llm_base_url.return_value = "https://openrouter.ai/api/v1"

        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Weather Forecast Query"}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        # Mock the get_api_key function
        with patch("services.openrouter.get_api_key", return_value="test-key"):
            with patch("services.history.update_conversation_title") as mock_update_title:
                with patch("database.SessionLocal") as mock_session:
                    mock_db = MagicMock()
                    mock_session.return_value = mock_db
                    
                    await generate_title_background("What's the weather?", "conv123", "gpt-4o")

                    # Verify title update was called
                    mock_update_title.assert_called_once_with(
                        mock_db, "conv123", "Weather Forecast Query"
                    )

    @pytest.mark.asyncio
    @patch("services.openrouter.settings")
    @patch("services.openrouter.httpx.AsyncClient")
    async def test_title_generation_emulator_model_autodetect(self, mock_client_class, mock_settings):
        """When using emulator, title generation should auto-detect the loaded model."""
        mock_settings.is_internal_llm.return_value = True
        mock_settings.get_llm_base_url.return_value = "http://emulator:8000/api/v1"

        # Mock /models response for auto-detection
        mock_models_response = MagicMock()
        mock_models_response.status_code = 200
        mock_models_response.json.return_value = {
            "data": [{"id": "Qwen/Qwen2.5-0.5B-Instruct"}]
        }

        # Mock chat completion response
        mock_chat_response = MagicMock()
        mock_chat_response.status_code = 200
        mock_chat_response.json.return_value = {
            "choices": [{"message": {"content": "Test Title"}}]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_models_response)
        mock_client.post = AsyncMock(return_value=mock_chat_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        with patch("services.openrouter.get_api_key", return_value="internal-key"):
            with patch("services.openrouter.history"):
                with patch("database.SessionLocal"):
                    await generate_title_background("Hello", "conv456", "qwen2.5-vl-72b-instruct")

                    # Verify the POST was called with the auto-detected model, not the UI model
                    call_args = mock_client.post.call_args
                    payload = call_args.kwargs.get("json") or call_args[1].get("json")
                    assert payload["model"] == "Qwen/Qwen2.5-0.5B-Instruct"

    @pytest.mark.asyncio
    @patch("services.openrouter.settings")
    async def test_title_generation_no_api_key(self, mock_settings):
        """Without an API key, title generation should exit early."""
        with patch("services.openrouter.get_api_key", return_value=""):
            # Should not raise any exceptions
            await generate_title_background("Hello", "conv789", "model")

    @pytest.mark.asyncio
    @patch("services.openrouter.settings")
    @patch("services.openrouter.httpx.AsyncClient")
    async def test_title_generation_llm_error(self, mock_client_class, mock_settings):
        """If the LLM returns an error, it should log and not crash."""
        mock_settings.is_internal_llm.return_value = False
        mock_settings.get_llm_base_url.return_value = "https://openrouter.ai/api/v1"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        with patch("services.openrouter.get_api_key", return_value="test-key"):
            # Should not raise
            await generate_title_background("Test", "conv999", "model")

    @pytest.mark.asyncio
    @patch("services.openrouter.settings")
    @patch("services.openrouter.httpx.AsyncClient")
    async def test_title_strips_quotes(self, mock_client_class, mock_settings):
        """Generated titles should have quotes stripped."""
        mock_settings.is_internal_llm.return_value = False
        mock_settings.get_llm_base_url.return_value = "https://openrouter.ai/api/v1"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '"Weather Query"'}}]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        with patch("services.openrouter.get_api_key", return_value="test-key"):
            with patch("services.history.update_conversation_title") as mock_update_title:
                with patch("database.SessionLocal") as mock_session:
                    mock_db = MagicMock()
                    mock_session.return_value = mock_db

                    await generate_title_background("What's the weather?", "conv321", "model")

                    # Verify quotes were stripped
                    call_args = mock_update_title.call_args
                    title = call_args[0][2]
                    assert '"' not in title
