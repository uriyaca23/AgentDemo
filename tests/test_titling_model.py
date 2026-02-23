import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from services.openrouter import generate_title_background

@pytest.mark.asyncio
async def test_generate_title_background_uses_provided_model():
    """Verifies that the titration background task uses the provided model string in its payload."""
    prompt = "Test prompt"
    conv_id = "test-conv"
    target_model = "anthropic/claude-3-opus"
    
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mocking a successful OpenRouter Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test Title"}}]
        }
        mock_post.return_value = mock_response
        
        # We need to mock get_api_key too
        with patch("services.openrouter.get_api_key", return_value="fake-key"):
            # Mock history and database session
            with patch("database.SessionLocal") as mock_session_local:
                with patch("services.history.update_conversation_title") as mock_update:
                    await generate_title_background(prompt, conv_id, target_model)
                    
                    # Verify the model used in the payload
                    args, kwargs = mock_post.call_args
                    payload = kwargs.get("json", {})
                    assert payload.get("model") == target_model
                    print(f"Verified: model '{target_model}' was passed to OpenRouter payload.")
