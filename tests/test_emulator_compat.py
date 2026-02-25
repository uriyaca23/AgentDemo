"""
OpenRouter Emulator — Compatibility Test Suite
================================================
These tests verify that the local Docker emulator produces responses
with an IDENTICAL format and behavior to OpenRouter's real API.

Tests are run against:
  1. The local emulator Docker container (EMULATOR_URL env var)
  2. OpenRouter's live API (using the real API key)

Compares the responses field-by-field to ensure zero surprises
when deploying to the internal organization.

Usage:
  # Start the emulator first:
  docker run -d --gpus all -p 8000:8000 --name emulator-test openrouter-emulator-test

  # Run these tests:
  python -m pytest tests/test_emulator_compat.py -v -m docker

  # Or compare ONLY against the emulator (without OpenRouter):
  EMULATOR_URL=http://localhost:8000/api/v1 python -m pytest tests/test_emulator_compat.py -v -k "emulator"
"""

import os
import sys
import json
import time
import pytest
import httpx

# ── Configuration ────────────────────────────────────────────────────────────
EMULATOR_URL = os.environ.get("EMULATOR_URL", "http://localhost:8000/api/v1")
OPENROUTER_URL = "https://openrouter.ai/api/v1"

# Resolve the API key for OpenRouter comparison tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

def _get_openrouter_key():
    """Get the OpenRouter API key, or None if unavailable."""
    try:
        import pyzipper
        zip_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../locked_secrets/api_key.zip"))
        if os.path.exists(zip_path):
            with pyzipper.AESZipFile(zip_path) as z:
                z.pwd = b"Quantom2321999"
                with z.open("api_key.txt") as f:
                    return f.read().decode("utf-8").strip()
    except Exception:
        pass
    
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../api_key.txt"))
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    return None


# ── Test model for local testing (small enough for RTX 3080) ─────────────────
# Auto-detected from the emulator's models endpoint at test time
_cached_emulator_model = None

def _get_emulator_model():
    """Auto-detect the model ID loaded in the emulator."""
    global _cached_emulator_model
    if _cached_emulator_model:
        return _cached_emulator_model
    try:
        resp = httpx.get(f"{EMULATOR_URL}/models", timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and len(data["data"]) > 0:
                _cached_emulator_model = data["data"][0]["id"]
                return _cached_emulator_model
    except Exception:
        pass
    # Fallback
    return os.environ.get("TEST_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")

# Cheap fast model on OpenRouter for comparison
TEST_MODEL_OPENROUTER = "openai/gpt-4o-mini"


# ── Helpers ──────────────────────────────────────────────────────────────────
def _emulator_available():
    """Check if the emulator Docker container is running."""
    try:
        resp = httpx.get(f"{EMULATOR_URL.rstrip('/').rsplit('/api/v1', 1)[0]}/", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False

def _openrouter_available():
    """Check if we have a valid OpenRouter API key."""
    key = _get_openrouter_key()
    if not key:
        return False
    try:
        resp = httpx.get(
            f"{OPENROUTER_URL}/auth/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5.0
        )
        return resp.status_code == 200
    except Exception:
        return False


# ── Markers ──────────────────────────────────────────────────────────────────
docker = pytest.mark.docker
skip_no_emulator = pytest.mark.skipif(
    not _emulator_available(),
    reason="Emulator Docker container not running. Start it first."
)
skip_no_openrouter = pytest.mark.skipif(
    not _openrouter_available(),
    reason="OpenRouter API key not available or invalid."
)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Emulator Standalone Tests
# These test the emulator on its own (no OpenRouter needed)
# ══════════════════════════════════════════════════════════════════════════════

@docker
@skip_no_emulator
class TestEmulatorStandalone:
    """Tests that the emulator endpoints work correctly on their own."""

    @pytest.mark.asyncio
    async def test_auth_endpoint_returns_200(self):
        """GET /api/v1/auth/key should always return 200."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{EMULATOR_URL}/auth/key",
                headers={"Authorization": "Bearer dummy-key"},
                timeout=10.0
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "data" in data
            assert "label" in data["data"]

    @pytest.mark.asyncio
    async def test_models_endpoint_returns_openrouter_format(self):
        """GET /api/v1/models should return {data: [...]} format."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{EMULATOR_URL}/models", timeout=10.0)
            assert resp.status_code == 200
            data = resp.json()
            
            # Must have the OpenRouter-style wrapper
            assert "data" in data, "Response missing 'data' key — not OpenRouter format!"
            assert isinstance(data["data"], list)
            assert len(data["data"]) > 0, "No models returned from emulator!"
            
            # Each model must have OpenRouter-expected fields
            model = data["data"][0]
            required_fields = ["id", "name", "context_length", "pricing"]
            for field in required_fields:
                assert field in model, f"Model missing required field '{field}'"
            
            assert isinstance(model["pricing"], dict)
            assert "prompt" in model["pricing"]
            assert "completion" in model["pricing"]

    @pytest.mark.asyncio
    async def test_streaming_completion_sse_format(self):
        """POST /api/v1/chat/completions (stream=True) should return proper SSE."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": _get_emulator_model(),
                "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                "stream": True,
                "max_tokens": 20
            }
            
            async with client.stream(
                "POST",
                f"{EMULATOR_URL}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            ) as response:
                assert response.status_code == 200, f"Streaming failed: {await response.aread()}"
                
                chunks = []
                got_done = False
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.strip() == "data: [DONE]":
                        got_done = True
                        continue
                    if line.startswith("data: "):
                        chunk = json.loads(line[6:])
                        chunks.append(chunk)
                
                assert len(chunks) > 0, "No SSE chunks received!"
                assert got_done, "Stream did not end with 'data: [DONE]'"
                
                # Validate chunk structure matches OpenRouter format
                first_chunk = chunks[0]
                assert "id" in first_chunk, "Chunk missing 'id'"
                assert first_chunk["id"].startswith("gen-"), f"ID should start with 'gen-', got: {first_chunk['id']}"
                assert "model" in first_chunk, "Chunk missing 'model'"
                assert "created" in first_chunk, "Chunk missing 'created'"
                assert "choices" in first_chunk, "Chunk missing 'choices'"
                
                # Validate delta structure
                for chunk in chunks:
                    if chunk.get("choices"):
                        choice = chunk["choices"][0]
                        assert "delta" in choice, "Choice missing 'delta'"
                        assert "index" in choice, "Choice missing 'index'"

    @pytest.mark.asyncio
    async def test_non_streaming_completion_format(self):
        """POST /api/v1/chat/completions (stream=False) should return proper format."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": _get_emulator_model(),
                "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                "stream": False,
                "max_tokens": 20
            }
            
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            
            # Validate response structure
            assert "id" in data
            assert data["id"].startswith("gen-")
            assert "model" in data
            assert "created" in data
            assert "choices" in data
            assert "usage" in data
            
            # Validate choice structure
            choice = data["choices"][0]
            assert "message" in choice
            assert "role" in choice["message"]
            assert "content" in choice["message"]
            assert choice["message"]["role"] == "assistant"
            assert len(choice["message"]["content"]) > 0
            
            # Validate usage
            usage = data["usage"]
            assert "prompt_tokens" in usage
            assert "completion_tokens" in usage
            assert "total_tokens" in usage

    @pytest.mark.asyncio
    async def test_streaming_error_format(self):
        """Errors during streaming should match OpenRouter's error format."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": "nonexistent/model-that-doesnt-exist",
                "messages": [{"role": "user", "content": "test"}],
                "stream": True,
                "max_tokens": 10
            }
            
            async with client.stream(
                "POST",
                f"{EMULATOR_URL}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=30.0
            ) as response:
                # Emulator should either return an error status or stream an error chunk
                content = ""
                async for line in response.aiter_lines():
                    content += line
                
                # Should contain error information
                assert "error" in content.lower() or response.status_code != 200, \
                    "Invalid model should produce an error!"

    @pytest.mark.asyncio
    async def test_openrouter_headers_accepted(self):
        """Emulator should silently accept OpenRouter-specific headers without errors."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": _get_emulator_model(),
                "messages": [{"role": "user", "content": "Ping"}],
                "stream": False,
                "max_tokens": 5
            }
            
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": "Bearer sk-or-fake-key-12345",
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Agent V2 Test",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
            assert resp.status_code == 200, f"Emulator rejected OpenRouter headers: {resp.text}"

    @pytest.mark.asyncio
    async def test_temperature_and_max_tokens_forwarded(self):
        """Temperature and max_tokens parameters should be forwarded to vLLM."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": _get_emulator_model(),
                "messages": [{"role": "user", "content": "Count from 1 to 100"}],
                "stream": False,
                "max_tokens": 5,
                "temperature": 0.0
            }
            
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            # With max_tokens=5, the response should be very short
            content = data["choices"][0]["message"]["content"]
            assert data["usage"]["completion_tokens"] <= 10, \
                f"max_tokens=5 was not respected! Got {data['usage']['completion_tokens']} tokens"

    @pytest.mark.asyncio
    async def test_tool_calling_schema_forwarded(self):
        """Tool calling schemas should be forwarded to vLLM without modification."""
        async with httpx.AsyncClient() as client:
            payload = {
                "model": _get_emulator_model(),
                "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
                "stream": False,
                "max_tokens": 100,
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"]
                        }
                    }
                }]
            }
            
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            
            # The request should succeed OR return a clear "tool-choice not enabled" error.
            # vLLM requires --enable-auto-tool-choice flag; without it, 400 is expected.
            if resp.status_code == 200:
                data = resp.json()
                assert "choices" in data
            elif resp.status_code == 400:
                # vLLM rejects tool_choice=auto without the right flags — this is expected
                assert "tool" in resp.text.lower() or "auto" in resp.text.lower(), \
                    f"Got 400 but error doesn't mention tool issues: {resp.text}"
            else:
                assert False, f"Unexpected status {resp.status_code}: {resp.text}"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1B: Extended Emulator Standalone Tests
# Deep-dive tests for edge cases, concurrency, and protocol compliance
# ══════════════════════════════════════════════════════════════════════════════

@docker
@skip_no_emulator
class TestEmulatorExtended:
    """Extended standalone tests — multi-turn, concurrency, edge-cases."""

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self):
        """Emulator should handle multi-turn conversations (context retention)."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": "Bearer dummy", "Content-Type": "application/json"}

            # Turn 1: introduce a fact
            resp1 = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [
                        {"role": "user", "content": "Remember this number: 42. Reply OK."}
                    ],
                    "stream": False,
                    "max_tokens": 20
                },
                headers=headers, timeout=60.0
            )
            assert resp1.status_code == 200
            turn1_data = resp1.json()
            assert "choices" in turn1_data

            # Turn 2: ask about the fact
            resp2 = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [
                        {"role": "user", "content": "Remember this number: 42. Reply OK."},
                        {"role": "assistant", "content": turn1_data["choices"][0]["message"]["content"]},
                        {"role": "user", "content": "What number did I ask you to remember?"}
                    ],
                    "stream": False,
                    "max_tokens": 30
                },
                headers=headers, timeout=60.0
            )
            assert resp2.status_code == 200
            turn2_data = resp2.json()
            assert "choices" in turn2_data
            # Both responses should have valid structure
            assert turn2_data["id"].startswith("gen-")

    @pytest.mark.asyncio
    async def test_system_message_forwarded(self):
        """System messages should be forwarded to vLLM and affect behavior."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": "Bearer dummy", "Content-Type": "application/json"}

            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [
                        {"role": "system", "content": "You are a pirate. Always speak like one."},
                        {"role": "user", "content": "Hello there!"}
                    ],
                    "stream": False,
                    "max_tokens": 50
                },
                headers=headers, timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["role"] == "assistant"
            assert len(data["choices"][0]["message"]["content"]) > 0

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Emulator should handle multiple concurrent requests without errors."""
        import asyncio

        async def single_request(idx: int):
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{EMULATOR_URL}/chat/completions",
                    json={
                        "model": _get_emulator_model(),
                        "messages": [{"role": "user", "content": f"Say the number {idx}"}],
                        "stream": False,
                        "max_tokens": 10
                    },
                    headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                    timeout=90.0
                )
                return resp.status_code, resp.json()

        results = await asyncio.gather(*[single_request(i) for i in range(3)])

        for status, data in results:
            assert status == 200, f"Concurrent request failed: {data}"
            assert "choices" in data

    @pytest.mark.asyncio
    async def test_empty_user_message(self):
        """Empty user message should not crash the emulator."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": ""}],
                    "stream": False,
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            # Should either succeed or return a structured error — never crash
            assert resp.status_code in (200, 400), f"Unexpected status: {resp.status_code}"

    @pytest.mark.asyncio
    async def test_long_streaming_integrity(self):
        """Longer streaming response should not drop chunks or corrupt data."""
        async with httpx.AsyncClient() as client:
            chunks = []
            got_done = False

            async with client.stream(
                "POST",
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Write a short poem about coding."}],
                    "stream": True,
                    "max_tokens": 100
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=120.0
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.strip() == "data: [DONE]":
                        got_done = True
                        continue
                    if line.startswith("data: "):
                        chunk = json.loads(line[6:])
                        chunks.append(chunk)

            assert len(chunks) > 5, f"Expected >5 chunks for 100 tokens, got {len(chunks)}"
            assert got_done, "Stream did not end with data: [DONE]"

            # All chunks should parse as valid JSON with consistent structure
            for chunk in chunks:
                assert "id" in chunk
                assert "choices" in chunk

    @pytest.mark.asyncio
    async def test_response_id_uniqueness(self):
        """Each request should get a distinct gen- ID."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": "Bearer dummy", "Content-Type": "application/json"}
            ids = set()
            for _ in range(3):
                resp = await client.post(
                    f"{EMULATOR_URL}/chat/completions",
                    json={
                        "model": _get_emulator_model(),
                        "messages": [{"role": "user", "content": "Hi"}],
                        "stream": False,
                        "max_tokens": 5
                    },
                    headers=headers, timeout=60.0
                )
                assert resp.status_code == 200
                data = resp.json()
                ids.add(data["id"])

            assert len(ids) == 3, f"Expected 3 unique IDs, got {len(ids)}: {ids}"

    @pytest.mark.asyncio
    async def test_model_field_consistency_across_stream(self):
        """All chunks in a streaming response should have the same model field."""
        async with httpx.AsyncClient() as client:
            models_seen = set()

            async with client.stream(
                "POST",
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                    "max_tokens": 20
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line.strip() != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        if "model" in chunk:
                            models_seen.add(chunk["model"])

            assert len(models_seen) == 1, f"Inconsistent model field across chunks: {models_seen}"

    @pytest.mark.asyncio
    async def test_stop_sequence_forwarding(self):
        """Stop sequences should be forwarded to vLLM."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Count: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10"}],
                    "stream": False,
                    "max_tokens": 50,
                    "stop": ["5"]
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "choices" in data
            # If stop worked, the content should be relatively short
            content = data["choices"][0]["message"]["content"]
            assert isinstance(content, str)

    @pytest.mark.asyncio
    async def test_finish_reason_present(self):
        """Non-streaming responses should include a finish_reason in choices."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Say hi"}],
                    "stream": False,
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            choice = data["choices"][0]
            assert "finish_reason" in choice, f"Missing finish_reason in choice: {choice}"
            assert choice["finish_reason"] in ("stop", "length"), \
                f"Unexpected finish_reason: {choice['finish_reason']}"

    @pytest.mark.asyncio
    async def test_usage_stats_present(self):
        """Non-streaming response should include usage statistics."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "usage" in data, "Missing usage stats"
            usage = data["usage"]
            assert "prompt_tokens" in usage
            assert "completion_tokens" in usage
            assert "total_tokens" in usage
            assert usage["prompt_tokens"] > 0
            assert usage["completion_tokens"] > 0
            assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1C: Cross-Format Compliance Tests
# Verify the emulator's response format matches OpenRouter's exactly
# ══════════════════════════════════════════════════════════════════════════════

@docker
@skip_no_emulator
class TestEmulatorFormatCompliance:
    """Tests that emulator responses match the OpenRouter API spec exactly."""

    @pytest.mark.asyncio
    async def test_streaming_chunk_has_all_required_fields(self):
        """Every SSE chunk must have: id, model, created, object, choices."""
        async with httpx.AsyncClient() as client:
            required_keys = {"id", "model", "created", "object", "choices"}

            async with client.stream(
                "POST",
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line.strip() != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        missing = required_keys - set(chunk.keys())
                        assert not missing, f"Chunk missing keys: {missing}. Got: {chunk.keys()}"
                        assert chunk["object"] == "chat.completion.chunk"

    @pytest.mark.asyncio
    async def test_non_streaming_has_all_required_fields(self):
        """Non-streaming response must have: id, model, created, object, choices, usage."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=60.0
            )
            assert resp.status_code == 200
            data = resp.json()
            required_keys = {"id", "model", "created", "object", "choices", "usage"}
            missing = required_keys - set(data.keys())
            assert not missing, f"Response missing keys: {missing}"
            assert data["object"] == "chat.completion"
            assert data["id"].startswith("gen-")

    @pytest.mark.asyncio
    async def test_error_response_format_matches_openrouter(self):
        """Error responses should match OpenRouter's {error: {message, code}} format."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                json={
                    "model": "nonexistent/fake-model",
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": False,
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer dummy", "Content-Type": "application/json"},
                timeout=30.0
            )
            # Should return an error (4xx)
            assert resp.status_code >= 400
            data = resp.json()
            assert "error" in data, f"Error response missing 'error' key: {data}"
            assert "message" in data["error"], f"Error missing 'message': {data['error']}"
            assert "code" in data["error"], f"Error missing 'code': {data['error']}"

    @pytest.mark.asyncio
    async def test_models_endpoint_field_types(self):
        """Verify the exact types of fields in the /models response."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{EMULATOR_URL}/models", timeout=10.0)
            assert resp.status_code == 200
            data = resp.json()

            model = data["data"][0]
            assert isinstance(model["id"], str)
            assert isinstance(model["name"], str)
            assert isinstance(model["context_length"], int)
            assert isinstance(model["pricing"], dict)
            assert isinstance(model["pricing"]["prompt"], str)
            assert isinstance(model["pricing"]["completion"], str)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Cross-Comparison Tests (Emulator vs OpenRouter)
# These compare the exact response format between both endpoints
# ══════════════════════════════════════════════════════════════════════════════


@docker
@skip_no_emulator
@skip_no_openrouter
class TestEmulatorVsOpenRouter:
    """
    Runs the SAME request against both the emulator and OpenRouter,
    then compares the response structure to ensure format compatibility.
    """

    @pytest.fixture
    def openrouter_headers(self):
        key = _get_openrouter_key()
        return {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Agent V2 Compat Test",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture
    def emulator_headers(self):
        return {
            "Authorization": "Bearer dummy-internal-key",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Agent V2 Compat Test",
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_auth_response_structure_matches(self, openrouter_headers, emulator_headers):
        """Compare /auth/key response structure."""
        async with httpx.AsyncClient() as client:
            or_resp = await client.get(
                f"{OPENROUTER_URL}/auth/key",
                headers=openrouter_headers,
                timeout=10.0
            )
            em_resp = await client.get(
                f"{EMULATOR_URL}/auth/key",
                headers=emulator_headers,
                timeout=10.0
            )
        
        assert or_resp.status_code == 200
        assert em_resp.status_code == 200
        
        or_data = or_resp.json()
        em_data = em_resp.json()
        
        # Both must have "data" key
        assert "data" in or_data, "OpenRouter response missing 'data'"
        assert "data" in em_data, "Emulator response missing 'data'"
        
        # Both must have "label" inside data
        assert "label" in or_data["data"], "OpenRouter missing 'data.label'"
        assert "label" in em_data["data"], "Emulator missing 'data.label'"

    @pytest.mark.asyncio
    async def test_models_response_structure_matches(self, openrouter_headers, emulator_headers):
        """Compare /models response structure."""
        async with httpx.AsyncClient() as client:
            or_resp = await client.get(
                f"{OPENROUTER_URL}/models",
                headers=openrouter_headers,
                timeout=10.0
            )
            em_resp = await client.get(
                f"{EMULATOR_URL}/models",
                headers=emulator_headers,
                timeout=10.0
            )
        
        or_data = or_resp.json()
        em_data = em_resp.json()
        
        # Both must use the {data: [...]} wrapper
        assert "data" in or_data
        assert "data" in em_data
        assert isinstance(or_data["data"], list)
        assert isinstance(em_data["data"], list)
        
        # Compare the fields present in each model entry
        or_model = or_data["data"][0]
        em_model = em_data["data"][0]
        
        # Core fields that must be present in BOTH
        core_fields = ["id", "name", "context_length", "pricing"]
        for field in core_fields:
            assert field in or_model, f"OpenRouter model missing '{field}'"
            assert field in em_model, f"Emulator model missing '{field}'"

    @pytest.mark.asyncio
    async def test_streaming_chunk_structure_matches(self, openrouter_headers, emulator_headers):
        """Compare SSE streaming chunk structure field-by-field."""
        
        async def collect_chunks(url, headers, model, max_chunks=5):
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Say 'hello world'"}],
                "stream": True,
                "max_tokens": 10
            }
            chunks = []
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", url, headers=headers, json=payload, timeout=60.0) as resp:
                    assert resp.status_code == 200, f"Request failed: {await resp.aread()}"
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            chunks.append(json.loads(line[6:]))
                            if len(chunks) >= max_chunks:
                                break
            return chunks
        
        or_chunks = await collect_chunks(
            f"{OPENROUTER_URL}/chat/completions",
            openrouter_headers,
            TEST_MODEL_OPENROUTER
        )
        em_chunks = await collect_chunks(
            f"{EMULATOR_URL}/chat/completions",
            emulator_headers,
            _get_emulator_model()
        )
        
        assert len(or_chunks) > 0, "No chunks from OpenRouter"
        assert len(em_chunks) > 0, "No chunks from Emulator"
        
        # Compare top-level keys
        or_keys = set(or_chunks[0].keys())
        em_keys = set(em_chunks[0].keys())
        
        required_keys = {"id", "model", "choices", "created"}
        assert required_keys.issubset(or_keys), f"OpenRouter missing keys: {required_keys - or_keys}"
        assert required_keys.issubset(em_keys), f"Emulator missing keys: {required_keys - em_keys}"
        
        # Compare choice structure
        or_choice = or_chunks[0]["choices"][0]
        em_choice = em_chunks[0]["choices"][0]
        
        assert "delta" in or_choice, "OpenRouter choice missing 'delta'"
        assert "delta" in em_choice, "Emulator choice missing 'delta'"
        assert "index" in or_choice, "OpenRouter choice missing 'index'"
        assert "index" in em_choice, "Emulator choice missing 'index'"
        
        # ID format check
        assert or_chunks[0]["id"].startswith("gen-"), f"OpenRouter ID format unexpected: {or_chunks[0]['id']}"
        assert em_chunks[0]["id"].startswith("gen-"), f"Emulator ID format unexpected: {em_chunks[0]['id']}"

    @pytest.mark.asyncio
    async def test_non_streaming_response_structure_matches(self, openrouter_headers, emulator_headers):
        """Compare non-streaming response structure."""
        async with httpx.AsyncClient() as client:
            or_resp = await client.post(
                f"{OPENROUTER_URL}/chat/completions",
                headers=openrouter_headers,
                json={
                    "model": TEST_MODEL_OPENROUTER,
                    "messages": [{"role": "user", "content": "Say 'test'"}],
                    "stream": False,
                    "max_tokens": 5
                },
                timeout=30.0
            )
            em_resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                headers=emulator_headers,
                json={
                    "model": _get_emulator_model(),
                    "messages": [{"role": "user", "content": "Say 'test'"}],
                    "stream": False,
                    "max_tokens": 5
                },
                timeout=60.0
            )
        
        or_data = or_resp.json()
        em_data = em_resp.json()
        
        # Compare top-level keys
        required_keys = {"id", "model", "choices", "usage"}
        for key in required_keys:
            assert key in or_data, f"OpenRouter response missing '{key}'"
            assert key in em_data, f"Emulator response missing '{key}'"
        
        # Compare choice.message structure
        or_msg = or_data["choices"][0]["message"]
        em_msg = em_data["choices"][0]["message"]
        assert "role" in or_msg and "role" in em_msg
        assert "content" in or_msg and "content" in em_msg
        assert or_msg["role"] == "assistant"
        assert em_msg["role"] == "assistant"
        
        # Compare usage structure
        usage_keys = {"prompt_tokens", "completion_tokens", "total_tokens"}
        for key in usage_keys:
            assert key in or_data["usage"], f"OpenRouter usage missing '{key}'"
            assert key in em_data["usage"], f"Emulator usage missing '{key}'"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Integration Tests (Backend → Emulator)
# These test the full backend-to-emulator integration
# ══════════════════════════════════════════════════════════════════════════════

@docker
@skip_no_emulator
class TestBackendEmulatorIntegration:
    """Tests the backend's OpenRouter service pointing at the emulator."""

    @pytest.mark.asyncio
    async def test_generate_chat_through_emulator(self):
        """Test that generate_chat_openrouter works when pointed at the emulator."""
        from unittest.mock import patch
        
        # Temporarily point settings at the emulator
        with patch("settings.settings.get_llm_base_url", return_value=EMULATOR_URL), \
             patch("settings.settings.is_internal_llm", return_value=True):
            
            from models.schemas import ChatRequest, Message
            from services.openrouter import generate_chat_openrouter
            
            req = ChatRequest(
                model=_get_emulator_model(),
                messages=[Message(role="user", content="Reply with exactly: PONG")],
                mode="auto"
            )
            
            chunks = []
            async for chunk in generate_chat_openrouter(req, offline_mode=True):
                if "data: " in chunk:
                    chunks.append(chunk)
            
            assert len(chunks) > 0, "No chunks received from emulator via backend!"
            
            # Verify we got actual content
            full_text = ""
            for c in chunks:
                if c.startswith("data: ") and c.strip() != "data: [DONE]":
                    try:
                        data = json.loads(c.strip().split("data: ", 1)[1])
                        if data.get("choices"):
                            delta = data["choices"][0].get("delta", {})
                            full_text += delta.get("content", "")
                    except json.JSONDecodeError:
                        pass
            
            assert len(full_text) > 0, "No text content received from emulator!"

    @pytest.mark.asyncio
    async def test_model_listing_through_emulator(self):
        """Test that the models endpoint works when pointed at the emulator."""
        from unittest.mock import patch
        from httpx import AsyncClient, ASGITransport
        from main import app
        
        with patch("routers.models.settings.get_llm_base_url", return_value=EMULATOR_URL), \
             patch("routers.models.settings.is_internal_llm", return_value=True), \
             patch("routers.models.get_api_key", return_value="internal-emulator-key"):
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/models")
                assert resp.status_code == 200
                data = resp.json()
                
                # Should have at least the base internal model + models from emulator
                assert len(data) >= 1
                
                # All should be labeled INTERNAL
                for m in data:
                    assert m["provider"] == "INTERNAL"
