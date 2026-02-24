import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from services.skills import process_skills, handle_generate_image, _build_pollinations_url
from models.db_models import ConversationDB


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = MagicMock()
    mock_conv = ConversationDB(id="test_id", title="Test", messages=[])
    db.query().filter().first.return_value = mock_conv
    return db


class _MockResponse:
    """Minimal httpx.Response substitute."""
    def __init__(self, status_code=200, content=b"", content_type="image/jpeg"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _MockHTTPXClient:
    """Async context-manager mock for httpx.AsyncClient."""
    def __init__(self, responses):
        self._responses = iter(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def get(self, *args, **kwargs):
        return next(self._responses)


# ── basic dispatch tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_skills_no_trigger():
    """Regular text must NOT trigger any skill."""
    result = await process_skills("Hello world!", None, None)
    assert result is None

@pytest.mark.asyncio
async def test_process_skills_empty_query_no_trigger(mock_db):
    """@generate_image with no query must not trigger the skill."""
    result = await process_skills("@generate_image", mock_db, "test_id")
    assert result is None

@pytest.mark.asyncio
async def test_process_skills_image_generation_trigger(mock_db):
    """@generate_image with a prompt must return an async generator."""
    result = await process_skills("@generate_image futuristic city", mock_db, "test_id")
    assert result is not None
    assert hasattr(result, "__aiter__")


# ── URL builder sanity check ─────────────────────────────────────────────────

def test_build_pollinations_url_contains_prompt():
    url = _build_pollinations_url("night sky stars", 42)
    assert "night" in url
    assert "sky" in url or "night%20sky" in url
    assert "nologo=true" in url
    assert "seed=42" in url


# ── success path: Pollinations returns a valid image ─────────────────────────

@pytest.mark.asyncio
@patch("services.skills.httpx.AsyncClient")
async def test_generate_image_success_pollinations(mock_cls, mock_db):
    """When Pollinations returns 200 with image bytes we get a markdown image chunk."""
    mock_cls.return_value = _MockHTTPXClient([
        _MockResponse(200, b"\x89PNG\r\n" + b"x" * 100, "image/png")
    ])

    chunks = [c async for c in handle_generate_image("a cool cat", mock_db, "test_id")]

    assert len(chunks) == 1
    payload = json.loads(chunks[0][6:])          # strip "data: "
    text = payload["choices"][0]["delta"]["content"]
    assert "![Generated Image]" in text
    assert "a cool cat" in text
    assert "⚠️" not in text


# ── retry path: Pollinations returns 530 twice then succeeds ─────────────────

@pytest.mark.asyncio
@patch("services.skills.asyncio.sleep", new_callable=AsyncMock)   # skip real sleeps
@patch("services.skills.httpx.AsyncClient")
async def test_generate_image_retries_on_530(mock_cls, mock_sleep, mock_db):
    """On a 530, we retry up to POLLINATIONS_MAX_ATTEMPTS before falling through."""
    fail = _MockResponse(530, b"error", "text/plain")
    ok   = _MockResponse(200, b"IMGBYTES", "image/jpeg")
    mock_cls.return_value = _MockHTTPXClient([fail, fail, ok])

    chunks = [c async for c in handle_generate_image("sunset", mock_db, "test_id")]

    payload = json.loads(chunks[0][6:])
    text = payload["choices"][0]["delta"]["content"]
    # Must NOT show the 530 error to the user — succeeded on 3rd try
    assert "530" not in text
    assert "![" in text


# ── permanent failure path: shows error message ────────────────────────────────

@pytest.mark.asyncio
@patch("services.skills.asyncio.sleep", new_callable=AsyncMock)
@patch("services.skills.httpx.AsyncClient")
async def test_generate_image_shows_error_on_permanent_failure(
    mock_cls, mock_sleep, mock_db
):
    """When all Pollinations attempts fail, we just show a friendly error without a fallback image."""
    mock_cls.return_value = _MockHTTPXClient([
        _MockResponse(530, b"", "text/plain"),
        _MockResponse(530, b"", "text/plain"),
        _MockResponse(530, b"", "text/plain"),
    ])

    chunks = [c async for c in handle_generate_image("abstract art", mock_db, "test_id")]

    payload = json.loads(chunks[0][6:])
    text = payload["choices"][0]["delta"]["content"]
    assert "⚠️" in text
    assert "failed" in text.lower() or "unavailable" in text.lower()



# ── pollinations availability probe (skipped when down) ──────────────────────

@pytest.mark.asyncio
async def test_pollinations_probe():
    """Probes Pollinations. Marks as SKIPPED (not failed) when it is down so CI stays green."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://image.pollinations.ai/prompt/dog?nologo=true&seed=1&width=64&height=64",
                timeout=10.0, follow_redirects=True
            )
        if r.status_code == 530:
            pytest.skip("Pollinations.ai is currently down (HTTP 530). Skipping live probe.")
        assert r.status_code == 200, f"Unexpected Pollinations status: {r.status_code}"
        assert r.headers.get("content-type", "").startswith("image/"), "Not an image response"
    except httpx.TimeoutException:
        pytest.skip("Pollinations.ai timed out. Skipping live probe.")
