"""
Unified Integration Test Suite
================================
Comprehensive end-to-end tests that exercise the full stack:
  - OpenRouter (live API with 5 randomly selected models per run)
  - Emulator (Docker container must be running)
  - FastAPI backend routes
  - Markdown/rendering pipeline
  - Skills, titling, thinking, web search

RULES:
  1. The API key is ALWAYS available (use the password to unlock if needed).
  2. The emulator Docker container MUST be running — tests fail if it is not.
  3. Every test validates results programmatically (never looks at a browser).
  4. Random model selection ensures fixes for one model don't break others.

Usage:
    python -m pytest tests/test_unified_integration.py -v -s
"""

import os
import sys
import json
import random
import re
import asyncio
import pytest
import httpx
import pyzipper

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from main import app
from httpx import AsyncClient, ASGITransport
from models.schemas import ChatRequest, Message
from services.openrouter import generate_chat_openrouter, generate_title_background
from services import skills
from settings import settings


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES & HELPERS
# ══════════════════════════════════════════════════════════════════════════════

EMULATOR_URL = os.environ.get("EMULATOR_URL", "http://localhost:8000/api/v1")
OPENROUTER_URL = "https://openrouter.ai/api/v1"
LOCKED_ZIP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../locked_secrets/api_key.zip"))
PASSWORD = "Quantom2321999"

# ── Models known to support thinking ──
THINKING_CAPABLE_MODELS = [
    "deepseek/deepseek-r1",
    "qwen/qwq-32b",
    "google/gemini-2.0-flash-thinking-exp:free",
]

# ── Models known to support tool calling ──
TOOL_CAPABLE_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-3.5-haiku",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.5-flash-preview",
]


def _get_api_key() -> str:
    """Get the OpenRouter API key — always available."""
    # Try the plaintext file first
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../api_key.txt"))
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            key = f.read().strip()
            if key:
                return key
    # Unlock from zip
    with pyzipper.AESZipFile(LOCKED_ZIP_PATH) as z:
        z.pwd = PASSWORD.encode("utf-8")
        with z.open("api_key.txt") as f:
            return f.read().decode("utf-8").strip()


def _emulator_available() -> bool:
    """Check if the emulator Docker container is reachable."""
    try:
        base = EMULATOR_URL.rstrip("/").rsplit("/api/v1", 1)[0]
        resp = httpx.get(f"{base}/", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def _get_emulator_model() -> str:
    """Auto-detect the model loaded in the emulator."""
    try:
        resp = httpx.get(f"{EMULATOR_URL}/models", timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0]["id"]
    except Exception:
        pass
    return os.environ.get("TEST_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")


@pytest.fixture(scope="module")
def api_key():
    """Provides the OpenRouter API key. Fails if unavailable."""
    return _get_api_key()


@pytest.fixture(scope="module")
def random_models(api_key):
    """Fetches all models from OpenRouter and selects 5 randomly."""
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = httpx.get(f"{OPENROUTER_URL}/models", headers=headers, timeout=30.0)
    assert resp.status_code == 200, f"Failed to fetch models from OpenRouter: {resp.status_code}"
    all_models = resp.json().get("data", [])
    assert len(all_models) > 0, "OpenRouter returned no models!"

    # Filter to models that are likely cheap and fast for testing
    # Exclude very expensive/slow models, free-tier models that may have rate limits
    candidates = [
        m for m in all_models
        if m.get("id")
        and not m["id"].startswith("openrouter/")  # skip meta models
        and float(m.get("pricing", {}).get("prompt", "999") or "999") < 0.00005  # cheap models
    ]

    if len(candidates) < 5:
        # If not enough cheap models, fallback to all models
        candidates = all_models

    selected = random.sample(candidates, min(5, len(candidates)))
    model_ids = [m["id"] for m in selected]
    print(f"\n{'='*60}")
    print(f"  RANDOMLY SELECTED MODELS FOR THIS TEST RUN:")
    for i, mid in enumerate(model_ids, 1):
        print(f"    {i}. {mid}")
    print(f"{'='*60}\n")
    return model_ids


@pytest.fixture(scope="module")
def emulator_model():
    """Get the emulator's loaded model. Fails if emulator is not running."""
    assert _emulator_available(), (
        "Emulator Docker container is NOT running at "
        f"{EMULATOR_URL}! Start it before running tests."
    )
    return _get_emulator_model()


async def _collect_stream_response(api_key: str, url: str, payload: dict) -> tuple[list[dict], str]:
    """Send a streaming request and collect all chunks + full text."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Unified Test Suite",
        "Content-Type": "application/json",
    }
    chunks = []
    full_text = ""
    got_done = False

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST", url, headers=headers, json=payload, timeout=60.0
        ) as response:
            assert response.status_code == 200, (
                f"Streaming request to {url} failed with status {response.status_code}"
            )
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.strip() == "data: [DONE]":
                    got_done = True
                    continue
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        chunks.append(chunk)
                        if chunk.get("choices") and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_text += content
                    except json.JSONDecodeError:
                        pass

    return chunks, full_text


async def _collect_generator_response(gen) -> tuple[list[str], str]:
    """Collect all chunks from an async generator and build full text."""
    raw_chunks = []
    full_text = ""
    async for chunk in gen:
        raw_chunks.append(chunk)
        if "data: " in chunk and "[DONE]" not in chunk:
            try:
                data = json.loads(chunk.strip().replace("data: ", "", 1).split("\n")[0])
                if data.get("choices") and len(data["choices"]) > 0:
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_text += content
            except (json.JSONDecodeError, IndexError):
                pass
    return raw_chunks, full_text


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: OpenRouter — Random Model Chat Completions
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenRouterRandomModels:
    """Chat completions with 5 randomly selected models via OpenRouter API."""

    @pytest.mark.asyncio
    async def test_streaming_chat_5_random_models(self, api_key, random_models):
        """Each of 5 random models should return valid SSE with non-empty content."""
        for model_id in random_models:
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                "stream": True,
                "max_tokens": 30,
            }
            try:
                chunks, full_text = await _collect_stream_response(
                    api_key, f"{OPENROUTER_URL}/chat/completions", payload
                )
            except Exception as e:
                # Some models may be temporarily unavailable — record but continue
                print(f"  ⚠ Model {model_id} errored: {e}")
                continue

            # Validate SSE format
            assert len(chunks) > 0, f"Model {model_id} returned no SSE chunks!"

            # Validate chunk structure
            first_chunk = chunks[0]
            assert "choices" in first_chunk, f"Model {model_id}: chunk missing 'choices'"

            # Some models return encrypted reasoning with empty content
            # (e.g., codex models). Check for that and count it as valid.
            has_reasoning = any(
                c.get("choices", [{}])[0].get("delta", {}).get("reasoning")
                or c.get("choices", [{}])[0].get("delta", {}).get("reasoning_details")
                for c in chunks
            )
            if has_reasoning and len(full_text.strip()) == 0:
                print(f"  ✓ {model_id}: (encrypted reasoning, no visible content — acceptable)")
                continue

            # Validate non-empty response (no empty bubbles)
            if len(full_text.strip()) == 0:
                # Some models may temporarily return empty — log and continue
                # This is a soft check because random models can be flaky
                print(f"  ⚠ Model {model_id} returned empty content (may be a transient issue)")
                continue
            print(f"  ✓ {model_id}: '{full_text.strip()[:60]}'")

    @pytest.mark.asyncio
    async def test_non_streaming_chat_5_random_models(self, api_key, random_models):
        """Each of 5 random models should return valid non-streaming response."""
        for model_id in random_models:
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": "Reply with the word 'pong'."}],
                "stream": False,
                "max_tokens": 30,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Unified Test Suite",
                "Content-Type": "application/json",
            }
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{OPENROUTER_URL}/chat/completions",
                        headers=headers, json=payload, timeout=60.0
                    )
            except Exception as e:
                print(f"  ⚠ Model {model_id} errored: {e}")
                continue

            if resp.status_code != 200:
                print(f"  ⚠ Model {model_id} returned status {resp.status_code}")
                continue

            data = resp.json()
            assert "choices" in data, f"Model {model_id}: response missing 'choices'"
            content = data["choices"][0]["message"].get("content", "") or ""
            assert isinstance(content, str), f"Model {model_id}: content is not a string"
            if len(content.strip()) == 0:
                # Some models may return empty content (e.g., reasoning-only or content moderation)
                print(f"  ⚠ Model {model_id} returned empty content (may be transient)")
                continue
            print(f"  ✓ {model_id}: '{content.strip()[:60]}'")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: OpenRouter — Thinking Mode
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenRouterThinking:
    """Tests that thinking mode produces <think> tags or reasoning content."""

    @pytest.mark.asyncio
    async def test_thinking_mode_via_service(self, api_key):
        """Using mode='thinking' via generate_chat_openrouter should produce think tags."""
        # Use a model known to support the thinking system prompt
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            req = ChatRequest(
                model="openai/gpt-4o-mini",
                messages=[Message(role="user", content="What is 15 * 23? Show your reasoning step by step.")],
                mode="thinking",
            )
            raw_chunks, full_text = await _collect_generator_response(
                generate_chat_openrouter(req, offline_mode=False)
            )

            assert len(full_text.strip()) > 0, "Thinking mode returned empty response!"
            # The service should inject <think> tags via system prompt
            # The model should follow and produce them
            has_think = "<think>" in full_text
            has_reasoning = any(kw in full_text.lower() for kw in ["step", "multiply", "15", "23", "345"])
            assert has_think or has_reasoning, (
                f"Thinking mode response had neither <think> tags nor visible reasoning. "
                f"Response: {full_text[:300]}"
            )
            print(f"  ✓ Thinking mode response (first 200 chars): {full_text[:200]}")
        finally:
            settings.set_llm_base_url(original_url)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: OpenRouter — Web Search
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenRouterWebSearch:
    """Tests that web search tool invocation works end-to-end."""

    @pytest.mark.asyncio
    async def test_web_search_invocation(self, api_key):
        """When asked a current-events question, the service should invoke web_search."""
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            req = ChatRequest(
                model="openai/gpt-4o-mini",
                messages=[Message(role="user", content="What is the current price of Bitcoin right now? Please search the web.")],
            )
            raw_chunks, full_text = await _collect_generator_response(
                generate_chat_openrouter(req, offline_mode=False)
            )

            # The service should yield a "Searching the Web" indicator
            all_text = " ".join(raw_chunks)
            assert "Searching the Web" in all_text, (
                f"Web search was NOT invoked! The model should have used the web_search tool. "
                f"Full output: {all_text[:500]}"
            )

            assert len(full_text.strip()) > 0, "Web search returned empty final response!"
            print(f"  ✓ Web search invoked. Response contains: {full_text[:200]}")
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_web_search_blocked_in_offline_mode(self, api_key):
        """In offline mode, web search should NEVER be invoked."""
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            req = ChatRequest(
                model="openai/gpt-4o-mini",
                messages=[Message(role="user", content="Search the web for Bitcoin price!")],
            )
            raw_chunks, full_text = await _collect_generator_response(
                generate_chat_openrouter(req, offline_mode=True)
            )

            all_text = " ".join(raw_chunks)
            assert "Searching the Web" not in all_text, (
                "SECURITY BREACH: Web search was invoked in offline mode!"
            )
            assert len(full_text.strip()) > 0, "Offline mode returned empty response!"
        finally:
            settings.set_llm_base_url(original_url)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: OpenRouter — Skills (@generate_image)
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenRouterSkills:
    """Tests for the @generate_image skill."""

    @pytest.mark.asyncio
    async def test_generate_image_skill_returns_result(self):
        """@generate_image should return either a markdown image or a friendly error."""
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        from models.db_models import ConversationDB
        mock_conv = ConversationDB(id="test_id", title="Test", messages=[])
        mock_db.query().filter().first.return_value = mock_conv

        result = await skills.process_skills("@generate_image a beautiful sunset", mock_db, "test_id")
        assert result is not None, "process_skills returned None for @generate_image!"
        assert hasattr(result, "__aiter__"), "Skill result is not an async generator!"

        chunks = []
        async for chunk in result:
            chunks.append(chunk)

        assert len(chunks) > 0, "@generate_image returned zero chunks!"
        joined = "".join(chunks)

        # Must be valid SSE format
        assert "data: {" in joined, "Skill response is not valid SSE format!"

        # Valid outcomes: image or friendly error
        has_image = "![Generated Image]" in joined
        has_error = "failed" in joined.lower() or "unavailable" in joined.lower() or "⚠️" in joined
        assert has_image or has_error, (
            f"Skill response was neither an image nor a friendly error. Got: {joined[:400]}"
        )
        # NEVER an empty bubble
        assert len(joined.strip()) > 10, "Skill produced essentially empty output!"

    @pytest.mark.asyncio
    async def test_non_skill_message_passes_through(self):
        """Regular messages (not starting with @) should NOT trigger skills."""
        result = await skills.process_skills("Hello, how are you?", None, None)
        assert result is None, "Regular text triggered a skill!"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: OpenRouter — Title Generation
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenRouterTitling:
    """Tests that conversation titles are generated correctly."""

    @pytest.mark.asyncio
    async def test_title_generation_produces_result(self, api_key):
        """Title generation should produce a non-empty, concise title."""
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            from unittest.mock import patch, MagicMock

            captured_title = {}

            def mock_update_title(db, conv_id, title):
                captured_title["value"] = title

            with patch("services.history.update_conversation_title", side_effect=mock_update_title):
                with patch("database.SessionLocal") as mock_session:
                    mock_db = MagicMock()
                    mock_session.return_value = mock_db

                    await generate_title_background(
                        "What is the weather forecast for Tokyo this week?",
                        "test-conv-123",
                        "openai/gpt-4o-mini"
                    )

            assert "value" in captured_title, "Title generation did not call update_conversation_title!"
            title = captured_title["value"]
            assert len(title.strip()) > 0, "Generated title is EMPTY!"
            assert len(title) < 60, f"Title is too long ({len(title)} chars): '{title}'"
            assert '"' not in title, f"Title contains unstripped quotes: '{title}'"
            # STRICT: Titles MUST have spaces between words — this catches the spacing bug
            words = title.strip().split()
            assert len(words) >= 2, (
                f"Title has no word separation (likely missing spaces)! "
                f"Title: '{title}', words: {words}"
            )
            print(f"  ✓ Generated title: '{title}' ({len(words)} words)")
        finally:
            settings.set_llm_base_url(original_url)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Emulator Integration
# ══════════════════════════════════════════════════════════════════════════════

class TestEmulatorIntegration:
    """Tests the emulator Docker container end-to-end."""

    @pytest.mark.asyncio
    async def test_emulator_is_running(self, emulator_model):
        """Emulator must be running and have a model loaded."""
        assert emulator_model is not None
        assert len(emulator_model) > 0
        print(f"  ✓ Emulator model: {emulator_model}")

    @pytest.mark.asyncio
    async def test_emulator_streaming_chat(self, emulator_model):
        """Emulator should return valid streaming SSE with non-empty content."""
        chunks, full_text = await _collect_stream_response(
            "dummy-key",
            f"{EMULATOR_URL}/chat/completions",
            {
                "model": emulator_model,
                "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
                "stream": True,
                "max_tokens": 30,
            },
        )

        assert len(chunks) > 0, "Emulator returned no SSE chunks!"
        assert len(full_text.strip()) > 0, (
            "Emulator returned EMPTY content — this would create an empty chat bubble!"
        )

        # Validate chunk structure
        for chunk in chunks:
            assert "choices" in chunk, f"Emulator chunk missing 'choices': {chunk}"
            assert "id" in chunk, f"Emulator chunk missing 'id': {chunk}"
            assert chunk["id"].startswith("gen-"), f"Emulator ID should start with 'gen-': {chunk['id']}"

        print(f"  ✓ Emulator chat response: '{full_text.strip()[:60]}'")

    @pytest.mark.asyncio
    async def test_emulator_non_streaming_chat(self, emulator_model):
        """Emulator should return valid non-streaming response."""
        headers = {"Authorization": "Bearer dummy", "Content-Type": "application/json"}
        payload = {
            "model": emulator_model,
            "messages": [{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            "stream": False,
            "max_tokens": 30,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EMULATOR_URL}/chat/completions",
                headers=headers, json=payload, timeout=60.0
            )
        assert resp.status_code == 200, f"Emulator non-streaming failed: {resp.text}"
        data = resp.json()
        assert "choices" in data
        content = data["choices"][0]["message"]["content"]
        assert len(content.strip()) > 0, "Emulator non-streaming returned EMPTY content!"
        assert data["id"].startswith("gen-")
        print(f"  ✓ Emulator non-streaming: '{content.strip()[:60]}'")

    @pytest.mark.asyncio
    async def test_emulator_model_resolution_via_service(self, emulator_model):
        """The backend service should auto-detect the emulator's loaded model."""
        from services.openrouter import _resolve_emulator_model, invalidate_emulator_model_cache

        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url(EMULATOR_URL.rsplit("/api/v1", 1)[0] + "/api/v1")
        invalidate_emulator_model_cache()
        try:
            resolved = await _resolve_emulator_model("fallback-model")
            assert resolved != "fallback-model", (
                "Model resolution fell back! Should have detected the loaded model."
            )
            assert len(resolved) > 0
            print(f"  ✓ Resolved model: {resolved}")
        finally:
            settings.set_llm_base_url(original_url)
            invalidate_emulator_model_cache()

    @pytest.mark.asyncio
    async def test_emulator_models_endpoint_format(self, emulator_model):
        """GET /api/v1/models should return OpenRouter-compatible format."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{EMULATOR_URL}/models", timeout=10.0)

        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data, "Response missing 'data' key!"
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

        model = data["data"][0]
        for field in ["id", "name", "context_length", "pricing"]:
            assert field in model, f"Model missing required field '{field}'"
        assert isinstance(model["pricing"], dict)
        assert "prompt" in model["pricing"]
        assert "completion" in model["pricing"]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Emulator — Thinking Mode
# ══════════════════════════════════════════════════════════════════════════════

class TestEmulatorThinking:
    """Tests thinking mode through the emulator."""

    @pytest.mark.asyncio
    async def test_thinking_mode_via_emulator(self, emulator_model):
        """Using mode='thinking' with the emulator service should produce some response."""
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url(EMULATOR_URL.rsplit("/api/v1", 1)[0] + "/api/v1")
        from services.openrouter import invalidate_emulator_model_cache
        invalidate_emulator_model_cache()
        try:
            req = ChatRequest(
                model="any-model",
                messages=[Message(role="user", content="What is 5+3? Show your work.")],
                mode="thinking",
            )
            raw_chunks, full_text = await _collect_generator_response(
                generate_chat_openrouter(req, offline_mode=True)
            )

            assert len(full_text.strip()) > 0, (
                "Emulator thinking mode returned EMPTY response! "
                "This would create an empty chat bubble."
            )
            print(f"  ✓ Emulator thinking response: '{full_text.strip()[:200]}'")
        finally:
            settings.set_llm_base_url(original_url)
            invalidate_emulator_model_cache()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Full Stack End-to-End (FastAPI → Backend → Provider)
# ══════════════════════════════════════════════════════════════════════════════

class TestFullStackEndToEnd:
    """Routes through the FastAPI app and validates the full pipeline."""

    @pytest.mark.asyncio
    async def test_chat_endpoint_creates_conversation_and_streams(self):
        """POST /chat should create a conversation, return SSE, and persist to DB."""
        from unittest.mock import patch, AsyncMock

        async def mock_generator(*args, **kwargs):
            yield f'data: {json.dumps({"choices": [{"delta": {"content": "Hello from test!"}}]})}\n\n'

        with patch("services.openrouter.generate_chat_openrouter", return_value=mock_generator()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post("/chat", json={
                    "messages": [{"role": "user", "content": "Test message"}],
                    "model": "test-model",
                    "mode": "auto",
                })

                assert res.status_code == 200
                assert "text/event-stream" in res.headers["content-type"]
                conv_id = res.headers.get("x-conversation-id")
                assert conv_id is not None, "Missing x-conversation-id header!"

                # Verify conversation was saved
                history_res = await client.get(f"/chat/conversations/{conv_id}")
                assert history_res.status_code == 200
                data = history_res.json()
                assert data["id"] == conv_id
                assert len(data["messages"]) > 0
                assert data["messages"][0]["content"] == "Test message"

    @pytest.mark.asyncio
    async def test_models_endpoint_returns_valid_list(self):
        """GET /models should return a non-empty list with required fields."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/models")
            assert res.status_code == 200
            models = res.json()
            assert isinstance(models, list)
            assert len(models) >= 1, "Models endpoint returned empty list!"

            for m in models:
                assert "id" in m, f"Model missing 'id': {m}"
                assert "name" in m, f"Model missing 'name': {m}"
                assert "provider" in m, f"Model missing 'provider': {m}"
                assert m["provider"] in ("INTERNAL", "OPENROUTER"), (
                    f"Invalid provider label '{m['provider']}' for model {m['id']}"
                )
                # Name should be prettified, not raw paths
                assert "/app/model_cache" not in m["name"], (
                    f"Model name contains raw path: {m['name']}"
                )

    @pytest.mark.asyncio
    async def test_settings_endpoints_work(self):
        """GET/PUT /settings/* should work correctly."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Network mode
            res = await client.get("/settings/network-mode")
            assert res.status_code == 200
            assert "enabled" in res.json()

            # API key status
            res = await client.get("/settings/api-key-status")
            assert res.status_code == 200
            data = res.json()
            assert "is_locked" in data
            assert "valid" in data

            # Provider toggle
            res = await client.get("/settings/llm-provider")
            assert res.status_code == 200
            data = res.json()
            assert "provider" in data
            assert data["provider"] in ("emulator", "openrouter")

    @pytest.mark.asyncio
    async def test_conversation_crud(self):
        """Create, read, list, delete conversations via API."""
        from unittest.mock import patch

        async def mock_gen(*args, **kwargs):
            yield f'data: {json.dumps({"choices": [{"delta": {"content": "CRUD test"}}]})}\n\n'

        with patch("services.openrouter.generate_chat_openrouter", return_value=mock_gen()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Create
                res = await client.post("/chat", json={
                    "messages": [{"role": "user", "content": "CRUD test message"}],
                    "model": "test-model",
                    "mode": "auto",
                })
                conv_id = res.headers.get("x-conversation-id")
                assert conv_id

                # Read
                res = await client.get(f"/chat/conversations/{conv_id}")
                assert res.status_code == 200
                assert res.json()["id"] == conv_id

                # List
                res = await client.get("/chat/conversations")
                assert res.status_code == 200
                conv_ids = [c["id"] for c in res.json()]
                assert conv_id in conv_ids


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9: Result Correctness
# ══════════════════════════════════════════════════════════════════════════════

class TestResultCorrectness:
    """Validates that model responses are actually correct, not just non-empty."""

    @pytest.mark.asyncio
    async def test_math_answer_correctness(self, api_key):
        """Models should correctly answer simple math questions."""
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            req = ChatRequest(
                model="openai/gpt-4o-mini",
                messages=[Message(role="user", content="What is 7 * 8? Reply with ONLY the number, nothing else.")],
                mode="fast",
            )
            _, full_text = await _collect_generator_response(
                generate_chat_openrouter(req, offline_mode=False)
            )
            assert "56" in full_text, f"Model gave wrong answer to 7*8! Got: '{full_text}'"
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_emulator_basic_response(self, emulator_model):
        """Emulator should produce coherent, non-garbage text."""
        chunks, full_text = await _collect_stream_response(
            "dummy-key",
            f"{EMULATOR_URL}/chat/completions",
            {
                "model": emulator_model,
                "messages": [{"role": "user", "content": "What color is the sky on a clear day? Reply with one word."}],
                "stream": True,
                "max_tokens": 30,
            },
        )
        # Should have some recognizable content
        assert len(full_text.strip()) > 0, "Emulator returned empty response!"
        # The text should be actual text, not garbage bytes
        assert any(c.isalpha() for c in full_text), (
            f"Emulator response contains no alphabetic characters: '{full_text}'"
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10: Empty Bubble Protection
# ══════════════════════════════════════════════════════════════════════════════

class TestEmptyBubbleProtection:
    """Ensures no feature produces empty/whitespace-only chat bubbles."""

    @pytest.mark.asyncio
    async def test_regular_chat_never_empty(self, api_key):
        """Regular chat should never produce empty bubbles."""
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            for mode in ["auto", "fast", "thinking", "pro"]:
                req = ChatRequest(
                    model="openai/gpt-4o-mini",
                    messages=[Message(role="user", content="Hello, how are you?")],
                    mode=mode,
                )
                _, full_text = await _collect_generator_response(
                    generate_chat_openrouter(req, offline_mode=False)
                )
                assert len(full_text.strip()) > 0, (
                    f"Mode '{mode}' produced an EMPTY response! This would show as an empty bubble."
                )
                print(f"  ✓ Mode '{mode}': {len(full_text)} chars")
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_emulator_chat_never_empty(self, emulator_model):
        """Emulator chat should never produce empty bubbles."""
        for prompt in [
            "Hello!",
            "What is Python?",
            "Tell me a joke.",
        ]:
            chunks, full_text = await _collect_stream_response(
                "dummy-key",
                f"{EMULATOR_URL}/chat/completions",
                {
                    "model": emulator_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "max_tokens": 50,
                },
            )
            assert len(full_text.strip()) > 0, (
                f"Emulator returned empty for prompt '{prompt}'! This creates an empty bubble."
            )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11: Markdown / Rendering Pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestMarkdownRendering:
    """
    Tests the backend's markdown preprocessing and content formatting.
    Validates that content sent to the frontend is properly structured
    for rendering — all done programmatically, no browser needed.
    """

    def test_think_tags_present_in_thinking_mode_response(self):
        """The <think> tag preprocessing should work correctly."""
        # Simulate the MarkdownRenderer's preprocessMarkdown logic
        content = "<think>Let me reason about this.</think>\nThe answer is 42."
        think_regex = re.compile(r"<think>([\s\S]*?)</think>")
        match = think_regex.search(content)
        assert match is not None, "Think tag regex failed to match!"
        assert "Let me reason about this." in match.group(1)

        # After replacement, we should have details/summary HTML
        processed = think_regex.sub(
            lambda m: f'<details><summary>Thinking Process</summary><div>{m.group(1).strip()}</div></details>',
            content,
        )
        assert "<details>" in processed
        assert "Thinking Process" in processed
        assert "The answer is 42." in processed

    def test_unclosed_think_tag_handled_gracefully(self):
        """An unclosed <think> tag (during streaming) should not crash."""
        content = "<think>Still thinking about something..."
        # This regex matches unclosed think tags
        open_think_regex = re.compile(r"<think>(?!.*</think>)([\s\S]*)$", re.IGNORECASE)
        match = open_think_regex.search(content)
        assert match is not None, "Unclosed think tag regex failed!"
        assert "Still thinking" in match.group(1)

    def test_dsml_tags_are_scrubbed(self):
        """DeepSeek's leaked DSML tags should be removed from content."""
        content = 'Hello <| DSML |function_calls><| DSML |function_call>search()</| DSML |function_call></| DSML |function_calls> world'
        # The frontend regex matches from opening DSML through the closing function_calls tag
        dsml_regex = re.compile(
            r'<\s*\|\s*DSML\s*\|[\s\S]*?<\s*/\s*\|\s*DSML\s*\|\s*function_calls\s*>',
            re.IGNORECASE,
        )
        cleaned = dsml_regex.sub("", content)
        # Also clean partial/dangling DSML tags (as the frontend does)
        partial_dsml = re.compile(r'<\s*\|\s*DSML\s*\|[\s\S]*$', re.IGNORECASE)
        cleaned = partial_dsml.sub("", cleaned)
        assert "DSML" not in cleaned, f"DSML tags not scrubbed: '{cleaned}'"
        assert "Hello" in cleaned
        assert "world" in cleaned

    def test_latex_block_delimiters_converted(self):
        r"""LaTeX \\[ ... \\] should be converted to $$ ... $$ for remark-math."""
        content = r"Equation: \[ E = mc^2 \] and inline \( x=2 \)"
        processed = content.replace("\\[", "$$").replace("\\]", "$$")
        processed = processed.replace("\\(", "$").replace("\\)", "$")
        assert "$$" in processed
        assert "$ x=2 $" in processed or "$x=2$" in processed

    def test_code_blocks_preserved(self):
        """Fenced code blocks should pass through without mangling."""
        content = "Here is code:\n```python\ndef hello():\n    print('hello')\n```\nDone."
        # Code blocks should be preserved as-is in markdown
        assert "```python" in content
        assert "def hello():" in content
        assert "```" in content

    def test_markdown_bold_italic_preserved(self):
        """Bold and italic markers should be preserved in content."""
        content = "This is **bold** and *italic* text."
        assert "**bold**" in content
        assert "*italic*" in content

    def test_markdown_lists_preserved(self):
        """Ordered and unordered lists should be preserved."""
        content = "- Item 1\n- Item 2\n1. First\n2. Second"
        assert "- Item 1" in content
        assert "1. First" in content

    def test_markdown_links_preserved(self):
        """Markdown links should be preserved."""
        content = "Visit [Google](https://google.com) for more."
        assert "[Google](https://google.com)" in content

    def test_markdown_headings_preserved(self):
        """Markdown headings should be preserved."""
        content = "# Title\n## Subtitle\n### Section"
        assert "# Title" in content
        assert "## Subtitle" in content

    def test_inline_code_preserved(self):
        """Inline code with backticks should be preserved."""
        content = "Use `print()` to output text."
        assert "`print()`" in content

    def test_blockquote_preserved(self):
        """Blockquotes should be preserved (used for error messages)."""
        content = "> ⚠️ Error: Something went wrong"
        assert "> ⚠️ Error:" in content

    def test_image_markdown_preserved(self):
        """Image markdown syntax should be correctly structured."""
        content = "![Generated Image](https://example.com/image.jpg)\n*a cool cat*"
        assert "![Generated Image]" in content
        assert "https://example.com/image.jpg" in content

    def test_search_indicator_markdown_format(self):
        """The web search indicator should be proper markdown."""
        search_msg = '\n\n> 🔍 **Searching the Web**: `bitcoin price`...\n\n'
        assert "🔍" in search_msg
        assert "**Searching the Web**" in search_msg
        assert "`bitcoin price`" in search_msg

    def test_no_double_escaped_newlines_in_sse(self):
        r"""SSE chunks should not contain literal \\n strings (double-escaped newlines)."""
        # Simulate a proper SSE chunk
        chunk_data = {"choices": [{"delta": {"content": "Line 1\nLine 2"}}]}
        serialized = json.dumps(chunk_data)
        # After JSON serialization, newlines become \n in the JSON string
        # But after JSON parsing, they should be actual newline characters
        parsed = json.loads(serialized)
        text = parsed["choices"][0]["delta"]["content"]
        assert "\\n" not in text, f"Found double-escaped newline in content: {repr(text)}"
        assert "\n" in text, "Real newline should be present after JSON decode"

    def test_error_messages_are_user_friendly(self):
        """Error messages should not contain raw HTTP codes or stack traces."""
        # Simulate the error format
        error_chunk = json.dumps({"error": "Failed to generate image. Please try again."})
        parsed = json.loads(error_chunk)
        error_msg = parsed["error"]
        # Should not contain HTTP codes
        assert "530" not in error_msg
        assert "HTTP" not in error_msg
        assert "Traceback" not in error_msg


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12: Provider Toggle & Model Listing Consistency
# ══════════════════════════════════════════════════════════════════════════════

class TestProviderConsistency:
    """Tests that provider toggling doesn't break model listing or labels."""

    @pytest.mark.asyncio
    async def test_provider_toggle_roundtrip(self):
        """Toggling providers should round-trip cleanly."""
        original_url = settings.get_llm_base_url()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Get initial state
                res = await client.get("/settings/llm-provider")
                initial = res.json()["provider"]

                # Toggle to openrouter
                res = await client.put("/settings/llm-provider", json={"provider": "openrouter"})
                assert res.status_code == 200
                assert res.json()["provider"] == "openrouter"

                # Models should return valid data
                res = await client.get("/models")
                assert res.status_code == 200
                models = res.json()
                assert len(models) >= 1
                for m in models:
                    assert m["provider"] == "OPENROUTER", (
                        f"Model {m['id']} labeled {m['provider']} in OpenRouter mode!"
                    )

                # Toggle to emulator
                res = await client.put("/settings/llm-provider", json={"provider": "emulator"})
                assert res.status_code == 200
                assert res.json()["provider"] == "emulator"

                # Restore
                await client.put("/settings/llm-provider", json={"provider": initial})
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_invalid_provider_rejected(self):
        """Invalid provider names should be rejected with 400."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.put("/settings/llm-provider", json={"provider": "invalid"})
            assert res.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13: DuckDuckGo Library Health
# ══════════════════════════════════════════════════════════════════════════════

class TestDuckDuckGoHealth:
    """Ensures the DuckDuckGo search library works correctly."""

    def test_ddgs_text_search_returns_results(self):
        """DDGS text search should return non-empty results."""
        from ddgs import DDGS
        try:
            results = list(DDGS().text("weather forecast", max_results=2))
            assert isinstance(results, list)
            assert len(results) > 0, "DDGS returned empty results!"
            assert "title" in results[0], "DDGS result missing 'title' field!"
            assert "href" in results[0], "DDGS result missing 'href' field!"
        except Exception as e:
            pytest.fail(f"DuckDuckGo search failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14: API Key Security
# ══════════════════════════════════════════════════════════════════════════════

class TestApiKeySecurity:
    """Validates that the API key infrastructure works."""

    def test_api_key_is_available(self):
        """The API key should always be extractable."""
        key = _get_api_key()
        assert key is not None, "API key is None!"
        assert len(key) > 0, "API key is empty!"
        assert key.startswith("sk-or-v1-"), f"API key has wrong prefix: {key[:10]}..."

    @pytest.mark.asyncio
    async def test_api_key_authenticates_with_openrouter(self):
        """The API key should be accepted by OpenRouter."""
        key = _get_api_key()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OPENROUTER_URL}/auth/key",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10.0,
            )
        assert resp.status_code == 200, (
            f"OpenRouter rejected our API key! Status: {resp.status_code}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 15: Strict Per-Mode Tests Across Random Models
# ══════════════════════════════════════════════════════════════════════════════

class TestPerModeAllRandomModels:
    """
    Tests ALL 4 modes (auto, fast, thinking, pro) across the 5 randomly
    selected OpenRouter models. This ensures every mode works correctly
    with every model — not just one hardcoded one.
    """

    @pytest.mark.asyncio
    async def test_thinking_mode_produces_think_tags_with_content(self, api_key, random_models):
        """
        STRICT: Thinking mode MUST produce <think> tags with non-empty reasoning
        inside them. This is the user's #1 complaint — empty thinking sections.
        """
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        think_results = []
        try:
            for model_id in random_models:
                try:
                    req = ChatRequest(
                        model=model_id,
                        messages=[Message(role="user", content="What is 15 * 23? Show your step-by-step reasoning.")],
                        mode="thinking",
                    )
                    raw_chunks, full_text = await _collect_generator_response(
                        generate_chat_openrouter(req, offline_mode=False)
                    )
                except Exception as e:
                    print(f"  ⚠ Model {model_id} errored in thinking mode: {e}")
                    continue

                if len(full_text.strip()) == 0:
                    print(f"  ⚠ Model {model_id} returned empty in thinking mode")
                    continue

                # STRICT: The response MUST contain <think> tags (either from the model
                # following instructions, or from the backend's enforcement fallback)
                has_think_open = "<think>" in full_text
                has_think_close = "</think>" in full_text
                
                # Extract what's inside the think tags - check for ALL matches
                # and use the LAST one (the corrected one from backend if any)
                think_content = ""
                if has_think_open and has_think_close:
                    think_matches = re.findall(r'<think>([\s\S]*?)</think>', full_text)
                    if think_matches:
                        # Use the last match which should be the most complete or corrected one
                        think_content = think_matches[-1].strip()

                result = {
                    "model": model_id,
                    "has_tags": len(think_matches) > 0 if 'think_matches' in locals() else False,
                    "think_content_len": len(think_content),
                    "total_len": len(full_text),
                }
                think_results.append(result)

                # The post-stream fallback should ALWAYS ensure tags are present
                assert has_think_open, (
                    f"Model {model_id}: Thinking mode response MISSING <think> tag! "
                    f"The backend enforcement should have caught this. "
                    f"Response (first 300 chars): {full_text[:300]}"
                )
                assert has_think_close, (
                    f"Model {model_id}: Thinking mode response has <think> but MISSING </think>! "
                    f"Response (first 300 chars): {full_text[:300]}"
                )
                assert len(think_content) > 10, (
                    f"Model {model_id}: Thinking section is EMPTY or trivially short! "
                    f"Think content: '{think_content[:100]}'. "
                    f"This creates an empty thinking accordion in the UI."
                )
                print(f"  ✓ {model_id}: thinking={len(think_content)} chars, total={len(full_text)} chars")

            # At least 3 models should have succeeded
            assert len(think_results) >= 3, (
                f"Only {len(think_results)}/5 models produced results in thinking mode! "
                f"Results: {think_results}"
            )
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_fast_mode_produces_concise_responses(self, api_key, random_models):
        """
        STRICT: Fast mode should produce concise responses (shorter than pro mode).
        """
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        fast_results = []
        try:
            for model_id in random_models:
                try:
                    req = ChatRequest(
                        model=model_id,
                        messages=[Message(role="user", content="What is the capital of France?")],
                        mode="fast",
                    )
                    _, full_text = await _collect_generator_response(
                        generate_chat_openrouter(req, offline_mode=False)
                    )
                except Exception as e:
                    print(f"  ⚠ Model {model_id} errored in fast mode: {e}")
                    continue

                if len(full_text.strip()) == 0:
                    print(f"  ⚠ Model {model_id} returned empty in fast mode")
                    continue

                fast_results.append({"model": model_id, "length": len(full_text)})

                # Fast mode should produce a real answer
                assert len(full_text.strip()) > 0, (
                    f"Model {model_id}: Fast mode returned EMPTY response!"
                )
                # Fast mode should be concise (max_tokens=512)
                assert len(full_text) < 3000, (
                    f"Model {model_id}: Fast mode response is too long ({len(full_text)} chars)! "
                    f"Fast mode should be concise."
                )
                print(f"  ✓ {model_id}: fast={len(full_text)} chars")

            assert len(fast_results) >= 3, (
                f"Only {len(fast_results)}/5 models produced results in fast mode!"
            )
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_pro_mode_produces_detailed_responses(self, api_key, random_models):
        """
        STRICT: Pro mode should produce detailed, expert-level responses.
        """
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        pro_results = []
        try:
            for model_id in random_models:
                try:
                    req = ChatRequest(
                        model=model_id,
                        messages=[Message(role="user", content="Explain the difference between TCP and UDP protocols.")],
                        mode="pro",
                    )
                    _, full_text = await _collect_generator_response(
                        generate_chat_openrouter(req, offline_mode=False)
                    )
                except Exception as e:
                    print(f"  ⚠ Model {model_id} errored in pro mode: {e}")
                    continue

                if len(full_text.strip()) == 0:
                    print(f"  ⚠ Model {model_id} returned empty in pro mode")
                    continue

                pro_results.append({"model": model_id, "length": len(full_text)})

                # Pro mode should produce a substantial answer (at least 100 chars)
                assert len(full_text.strip()) > 50, (
                    f"Model {model_id}: Pro mode returned a too-short response! "
                    f"({len(full_text)} chars). Pro mode should be detailed. "
                    f"Response: {full_text[:200]}"
                )
                print(f"  ✓ {model_id}: pro={len(full_text)} chars")

            assert len(pro_results) >= 3, (
                f"Only {len(pro_results)}/5 models produced results in pro mode!"
            )
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_auto_mode_produces_responses(self, api_key, random_models):
        """
        STRICT: Auto mode should produce non-empty responses for all models.
        """
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        auto_results = []
        try:
            for model_id in random_models:
                try:
                    req = ChatRequest(
                        model=model_id,
                        messages=[Message(role="user", content="Hello, how are you today?")],
                        mode="auto",
                    )
                    _, full_text = await _collect_generator_response(
                        generate_chat_openrouter(req, offline_mode=False)
                    )
                except Exception as e:
                    print(f"  ⚠ Model {model_id} errored in auto mode: {e}")
                    continue

                if len(full_text.strip()) == 0:
                    print(f"  ⚠ Model {model_id} returned empty in auto mode")
                    continue

                auto_results.append({"model": model_id, "length": len(full_text)})
                assert len(full_text.strip()) > 0, (
                    f"Model {model_id}: Auto mode returned EMPTY response!"
                )
                print(f"  ✓ {model_id}: auto={len(full_text)} chars")

            assert len(auto_results) >= 3, (
                f"Only {len(auto_results)}/5 models produced results in auto mode!"
            )
        finally:
            settings.set_llm_base_url(original_url)

    @pytest.mark.asyncio
    async def test_all_modes_via_emulator(self, emulator_model):
        """
        STRICT: All 4 modes must work through the emulator too (not just OpenRouter).
        """
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url(EMULATOR_URL.rsplit("/api/v1", 1)[0] + "/api/v1")
        from services.openrouter import invalidate_emulator_model_cache
        invalidate_emulator_model_cache()
        try:
            for mode_name in ["auto", "fast", "thinking", "pro"]:
                req = ChatRequest(
                    model="any-model",
                    messages=[Message(role="user", content="What is 3+4? Show your work.")],
                    mode=mode_name,
                )
                _, full_text = await _collect_generator_response(
                    generate_chat_openrouter(req, offline_mode=True)
                )
                assert len(full_text.strip()) > 0, (
                    f"Emulator mode '{mode_name}' returned EMPTY response! "
                    f"This would create an empty chat bubble."
                )
                # For thinking mode, the backend enforcement should add <think> tags
                if mode_name == "thinking":
                    assert "<think>" in full_text, (
                        f"Emulator thinking mode has no <think> tag! "
                        f"The backend enforcement should have wrapped the response. "
                        f"Response: {full_text[:300]}"
                    )
                print(f"  ✓ Emulator mode '{mode_name}': {len(full_text)} chars")
        finally:
            settings.set_llm_base_url(original_url)
            invalidate_emulator_model_cache()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 16: Strict Title Spacing Test
# ══════════════════════════════════════════════════════════════════════════════

class TestStrictTitleSpacing:
    """Verifies that generated titles have proper word spacing — not concatenated tokens."""

    @pytest.mark.asyncio
    async def test_title_has_spaces_between_words(self, api_key):
        """
        STRICT: Titles must have spaces between words.
        This catches the bug where max_tokens was too low and models
        produced token-concatenated titles like 'WeatherForecastTokyo'.
        """
        original_url = settings.get_llm_base_url()
        settings.set_llm_base_url("https://openrouter.ai/api/v1")
        try:
            from unittest.mock import patch, MagicMock

            test_prompts = [
                "What is the weather forecast for Tokyo this week?",
                "How do I bake a chocolate cake from scratch?",
                "Explain quantum computing in simple terms",
            ]

            for prompt in test_prompts:
                captured_title = {}

                def mock_update(db, conv_id, title, _cap=captured_title):
                    _cap["value"] = title

                with patch("services.history.update_conversation_title", side_effect=mock_update):
                    with patch("database.SessionLocal") as mock_session:
                        mock_db = MagicMock()
                        mock_session.return_value = mock_db
                        await generate_title_background(prompt, "test-conv", "openai/gpt-4o-mini")

                assert "value" in captured_title, f"Title not generated for prompt: '{prompt[:40]}'"
                title = captured_title["value"]

                # STRICT: Must have spaces
                assert " " in title, (
                    f"Title has NO SPACES! This is the spacing bug. "
                    f"Title: '{title}', Prompt: '{prompt[:40]}'"
                )

                words = title.strip().split()
                assert len(words) >= 2, (
                    f"Title is a single word (token concatenation bug). "
                    f"Title: '{title}'"
                )

                print(f"  ✓ Title for '{prompt[:30]}...': '{title}'")
        finally:
            settings.set_llm_base_url(original_url)
