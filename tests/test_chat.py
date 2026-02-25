import os
import sys
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from main import app

@pytest.mark.asyncio
async def test_chat_creation_and_history():
    """Verify that sending a message creates history and returns an SSE stream."""
    
    # Mock the LLM service since we may not have an actual backend running
    async def mock_generator(*args, **kwargs):
        yield f'data: {json.dumps({"choices": [{"delta": {"content": "Hello from mock LLM"}}]})}\n\n'

    with patch("services.openrouter.generate_chat_openrouter", return_value=mock_generator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {
                "messages": [{"role": "user", "content": "Ping!"}],
                "model": "qwen2.5-vl-72b-instruct",
                "mode": "auto"
            }
            res = await client.post("/chat", json=payload)
            
            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]
            conv_id = res.headers.get("x-conversation-id")
            assert conv_id is not None
            
            # Verify the DB actually saved it
            history_res = await client.get(f"/chat/conversations/{conv_id}")
            assert history_res.status_code == 200
            data = history_res.json()
            assert data["id"] == conv_id
            assert len(data["messages"]) > 0
            assert data["messages"][0]["content"] == "Ping!"

@pytest.mark.asyncio
async def test_chat_skill_interception():
    """Verify that sending @generate_image intercepts the LLM and hits the skill backend."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "messages": [{"role": "user", "content": "@generate_image a red car"}],
            "model": "gpt-4",
            "mode": "auto"
        }
        
        # We don't want to actually wait for pollination if the network is flaky, but we can test if it yields the right format or error.
        res = await client.post("/chat", json=payload)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        
        # It's an AsyncGenerator, we read it
        chunks = []
        async for line in res.aiter_lines():
            if line:
                chunks.append(line)
        
        assert len(chunks) > 0
        joined = "".join(chunks)
        # The skill must intercept and yield a structured SSE chunk.
        assert "data: {" in joined
        # Valid outcomes:
        #   1. Pollinations succeeded → contains "![Generated Image]"
        #   2. Everything failed → friendly error message with "failed" or "unavailable"
        has_image = "![Generated Image]" in joined
        has_error = "failed" in joined.lower() or "unavailable" in joined.lower()
        assert has_image or has_error, (
            f"Skill response was neither an image nor a friendly error.\nGot: {joined[:400]}"
        )

@pytest.mark.asyncio
async def test_chat_routes_all_models_through_llm_service():
    """Verify that ALL models (including internal) route through generate_chat_openrouter."""
    
    call_log = []
    
    async def tracking_generator(request, offline_mode, conv_id=None, db=None):
        call_log.append({"model": request.model, "offline_mode": offline_mode})
        yield f'data: {json.dumps({"choices": [{"delta": {"content": "Routed OK"}}]})}\n\n'
    
    with patch("routers.chat.openrouter.generate_chat_openrouter", side_effect=tracking_generator):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test internal model
            res = await client.post("/chat", json={
                "messages": [{"role": "user", "content": "Test"}],
                "model": "qwen2.5-vl-72b-instruct",
                "mode": "auto"
            })
            assert res.status_code == 200
            body = res.text
            assert "Routed OK" in body
            
            # Test external model
            res = await client.post("/chat", json={
                "messages": [{"role": "user", "content": "Test"}],
                "model": "openai/gpt-4o-mini",
                "mode": "auto"
            })
            assert res.status_code == 200
            body = res.text
            assert "Routed OK" in body
            
            # Both should have been routed through the LLM service
            assert len(call_log) == 2
            assert call_log[0]["model"] == "qwen2.5-vl-72b-instruct"
            assert call_log[1]["model"] == "openai/gpt-4o-mini"

