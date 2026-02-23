import os
import sys
import json
import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from main import app

@pytest.mark.asyncio
async def test_chat_creation_and_history():
    """Verify that sending a message creates history and returns an SSE stream."""
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
        #   2. Pollinations down, fallback image found → contains "![Relevant Image]"
        #   3. Everything failed → friendly error message with "failed" or "unavailable"
        has_image = "![Generated Image]" in joined or "![Relevant Image]" in joined
        has_error = "failed" in joined.lower() or "unavailable" in joined.lower()
        assert has_image or has_error, (
            f"Skill response was neither an image nor a friendly error.\nGot: {joined[:400]}"
        )
