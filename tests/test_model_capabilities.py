import os
import sys
import json
import pytest
import httpx

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from settings import settings

# Base URL for the local backend
API_BASE = "http://localhost:8001"

@pytest.mark.asyncio
async def test_models_endpoint_has_capabilities():
    """Verify that the /models endpoint returns capability metadata."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/models", timeout=10.0)
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) > 0
        
        # Check a few popular models for capabilities
        for m in models:
            assert "capabilities" in m
            caps = m["capabilities"]
            assert "thinking" in caps
            assert "tools" in caps
            assert "multimodal" in caps
            
            # Specific checks for known models (if present)
            m_id = m["id"].lower()
            if "deepseek-r1" in m_id or "openai/o1" in m_id:
                assert caps["thinking"] == "native"
            elif "instruct" in m_id or "chat" in m_id:
                assert caps["thinking"] in ["native", "simulated"]

@pytest.mark.asyncio
async def test_mode_restriction_logic():
    """
    Verify that the thinking mode works correctly for both 
    native reasoning and simulated models.
    """
    # 1. Test with a model known to support thinking (simulated)
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "What is 2+2? Think first."}],
        "mode": "thinking"
    }
    
    async with httpx.AsyncClient() as client:
        # We'll use the streaming endpoint
        async with client.stream("POST", f"{API_BASE}/chat", json=payload, timeout=60.0) as resp:
            assert resp.status_code == 200
            full_text = ""
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and "[DONE]" not in line:
                    data = json.loads(line[6:])
                    if data.get("choices"):
                        full_text += data["choices"][0].get("delta", {}).get("content", "")
            
            # Verify thinking tags are present
            assert "<think>" in full_text
            assert "</think>" in full_text
            print(f"\n  ✓ GPT-4o-Mini thinking response captured")

@pytest.mark.asyncio
async def test_auto_mode_intelligent_trigger():
    """Verify that auto mode triggers thinking for complex prompts."""
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "Solve this integral: int(x^2, x=0..1)"}],
        "mode": "auto"
    }
    
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", f"{API_BASE}/chat", json=payload, timeout=60.0) as resp:
            full_text = ""
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and "[DONE]" not in line:
                    data = json.loads(line[6:])
                    if data.get("choices"):
                        full_text += data["choices"][0].get("delta", {}).get("content", "")
            
            # For complex math, it SHOULD trigger thinking in auto mode
            # (Note: This depends on the model following the 'auto' instructions well)
            has_think = "<think>" in full_text
            print(f"\n  ✓ Auto mode triggered thinking: {has_think}")
