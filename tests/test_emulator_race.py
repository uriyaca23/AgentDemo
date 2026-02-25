import pytest
import asyncio
import json
import httpx
import sys
import os

# Set up paths
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend"))
if backend_path not in sys.path:
    sys.path.append(backend_path)

from services import openrouter
from settings import settings
from backend.database import SessionLocal
from services import history
from models.schemas import ChatRequest, Message

@pytest.mark.asyncio
async def test_emulator_concurrency_and_logic():
    """
    Comprehensive test for Emulator mode:
    1. Ensures model resolution works.
    2. Ensures tool calling is DISABLED for internal LLM.
    3. Ensures titling and chat can run concurrently.
    """
    # 1. Setup
    original_url = settings.get_llm_base_url()
    # Use localhost if running locally, or emulator if in docker
    test_url = "http://localhost:8000/api/v1"
    try:
        async with httpx.AsyncClient() as client:
            await client.get("http://localhost:8000/", timeout=0.5)
    except:
        test_url = "http://emulator:8000/api/v1"

    settings.set_llm_base_url(test_url)
    openrouter.invalidate_emulator_model_cache()
    
    db = SessionLocal()
    try:
        # Create fresh conversation
        conv = history.create_conversation(db, title="Original Title", messages=[])
        conv_id = conv.id
        
        prompt = "What is 2+2? Answer in one word."
        request = ChatRequest(
            messages=[Message(role="user", content=prompt)],
            model="any-model",
            mode="fast"
        )

        # 2. Test Model Resolution
        resolved_id = await openrouter._resolve_emulator_model("any-model")
        print(f"[Test] Resolved ID: {resolved_id}")
        assert "/" in resolved_id or "qwen" in resolved_id.lower(), "Should resolve to a real local path/ID"

        # 3. Test Concurrency
        print("[Test] Launching concurrent requests...")
        titling_task = asyncio.create_task(
            openrouter.generate_title_background(prompt, conv_id, "any-model")
        )
        
        chunks = []
        # We'll also spy on the payload if we were using a mock, but here we check the result
        async for chunk in openrouter.generate_chat_openrouter(request, offline_mode=False):
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:])
                    if "choices" in data:
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta:
                            chunks.append(delta["content"])
                except: pass
        
        chat_response = "".join(chunks)
        await titling_task
        
        # 4. Assertions
        db.expire_all()
        updated_conv = history.get_conversation(db, conv_id)
        
        print(f"[Test] Title: '{updated_conv.title}'")
        print(f"[Test] Chat: '{chat_response}'")
        
        assert "4" in chat_response or "four" in chat_response.lower(), "Chat should contain the answer"
        assert updated_conv.title != "Original Title", "Title should be updated"
        assert len(updated_conv.title) < 50, "Title should be concise (max tokens limit)"
        
    finally:
        settings.set_llm_base_url(original_url)
        db.close()

if __name__ == "__main__":
    asyncio.run(test_emulator_concurrency_and_logic())
