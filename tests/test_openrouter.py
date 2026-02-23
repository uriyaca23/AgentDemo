import os
import json
import pytest
import pyzipper
import httpx
from unittest.mock import patch

# Constants
LOCKED_ZIP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../locked_secrets/api_key.zip"))
PASSWORD = "Quantom2321999"

@pytest.fixture
def api_key():
    """Extracts and provides the actual API key for testing"""
    if not os.path.exists(LOCKED_ZIP_PATH):
        pytest.skip("locked_secrets/api_key.zip not found. Cannot test OpenRouter API.")
        
    try:
        with pyzipper.AESZipFile(LOCKED_ZIP_PATH) as z:
            z.pwd = PASSWORD.encode('utf-8')
            with z.open("api_key.txt") as f:
                return f.read().decode('utf-8').strip()
    except Exception as e:
        pytest.fail(f"Could not extract API key for test: {e}")

@pytest.mark.asyncio
async def test_openrouter_authentication(api_key):
    """Tests if the OpenRouter API accepts our decrypted key."""
    url = "https://openrouter.ai/api/v1/auth/key"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        
        # 401 means the key extracted correctly but OpenRouter says it's invalid/revoked.
        # 200 means the key is fully functional.
        assert response.status_code == 200, f"OpenRouter rejected the API key. Status: {response.status_code}, Body: {response.text}"

@pytest.mark.asyncio
async def test_openrouter_streaming_completion(api_key):
    """Verifies that we can successfully stream a completion from OpenRouter."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agent V2 Test Suite",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "openai/gpt-4o-mini",  # Fast, cheap test model
        "messages": [{"role": "user", "content": "Reply with precisely the word 'PONG'."}],
        "stream": True,
        "max_tokens": 10
    }
    
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream("POST", url, headers=headers, json=payload, timeout=30.0) as response:
                assert response.status_code == 200, f"Streaming request failed: {await response.aread()}"
                
                chunks_received = 0
                full_text = ""
                async for chunk in response.aiter_lines():
                    if chunk.startswith("data: ") and chunk != "data: [DONE]":
                        try:
                            data = json.loads(chunk[6:])
                            if data.get("choices") and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {}).get("content", "")
                                full_text += delta
                                chunks_received += 1
                        except json.JSONDecodeError:
                            pass
                            
                assert chunks_received > 0, "No valid data chunks received!"
                assert "PONG" in full_text.upper(), f"Model did not reply exactly 'PONG'. It said: {full_text}"
                
        except httpx.RequestError as e:
            pytest.fail(f"Network error during streaming test: {e}")

@pytest.mark.asyncio
async def test_openrouter_streaming_multimodal(api_key):
    """Verifies that the OpenRouter API accepts the [{type: 'text'}, {type: 'image_url'}] array format."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agent V2 Test Suite",
        "Content-Type": "application/json"
    }

    # Extremely tiny 1x1 Red Pixel PNG in Base64
    red_pixel_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": "Are you able to see images? What is the single dominant color of this simple 1x1 image? Reply with ONLY the color name (e.g. Blue)."},
                    {"type": "image_url", "image_url": {"url": red_pixel_b64}}
                ]
            }
        ],
        "stream": False,
        "max_tokens": 10
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            assert response.status_code == 200, f"Multimodal request failed: {response.text}"
            
            data = response.json()
            assert data.get("choices"), "No choices returned from Multimodal request!"
            content = data["choices"][0]["message"]["content"]
            
            assert "red" in content.lower(), f"Model failed to see the red pixel! It responded with: {content}"
            
        except httpx.RequestError as e:
            pytest.fail(f"Network error during multimodal test: {e}")

@pytest.mark.asyncio
async def test_openrouter_tool_calling_online(api_key):
    """Verifies that the OpenRouter API accepts our tool schema and correctly predicts a search."""
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
    
    from models.schemas import ChatRequest, Message
    from services.openrouter import generate_chat_openrouter
    
    req = ChatRequest(
        model="openai/gpt-4o-mini",
        messages=[Message(role="user", content="What is the current price of Bitcoin today? I need you to search the live web.")],
        stream=True
    )
    
    chunks_received = []
    # Offline = False should injecting the tool
    async for chunk in generate_chat_openrouter(req, offline_mode=False):
        if "data: " in chunk:
            chunks_received.append(chunk)
            
    # We should see the generator yield that it is searching the web
    assert any("Searching the Web" in c for c in chunks_received), "Model failed to invoke the web search tool!"
    
    # We must ensure there is NO double-escaping of newlines (e.g. leaking literal '\\n' into the UI)
    # The JSON string internally should map to true new line chars during JSON decoding.
    for c in chunks_received:
        if "Searching the Web" in c:
            data = json.loads(c[6:])
            text = data["choices"][0]["delta"]["content"]
            assert "\\n" not in text, f"Found literal string '\\n' instead of actual newline character! text: {repr(text)}"
    
@pytest.mark.asyncio
async def test_openrouter_tool_calling_offline(api_key):
    """Verifies that the OpenRouter API is BLOCKED from using tools when offline_mode=True."""
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
    
    from models.schemas import ChatRequest, Message
    from services.openrouter import generate_chat_openrouter
    
    req = ChatRequest(
        model="openai/gpt-4o-mini",
        messages=[Message(role="user", content="What is the current price of Bitcoin right now? You must search the web!")]
    )
    
    chunks_received = []
    # Offline = True strips tools and adds air-gapped system prompt
    async for chunk in generate_chat_openrouter(req, offline_mode=True):
        if "data: " in chunk:
            chunks_received.append(chunk)
            
    # It must NOT yield the Searching the Web indicator
    assert not any("Searching the Web" in c for c in chunks_received), "Security Breach: Model invoked a tool while in Offline Mode!"

@pytest.mark.asyncio
@patch("services.openrouter.httpx.AsyncClient")
async def test_openrouter_tool_fallback_for_unsupported_models(mock_httpx_class, api_key):
    """Verifies that if an OpenRouter model does not support tool use (returning 404/400), we gracefully retry without tools."""
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
    
    from models.schemas import ChatRequest, Message
    from services.openrouter import generate_chat_openrouter
    
    class MockStreamResponse:
        def __init__(self, with_tools):
            self.with_tools = with_tools
            self.status_code = 404 if with_tools else 200
            
        async def __aenter__(self):
            return self
            
        async def __aexit__(self, exc_type, exc, tb):
            pass
            
        async def aread(self):
            return b'{"error":{"message":"No endpoints found that support tool use.","code":404}}'
            
        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"PONG"}}]}'
            yield 'data: [DONE]'

    class MockClientContext:
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        
        def stream(self, method, url, **kwargs):
            payload = kwargs.get('json', {})
            with_tools = 'tools' in payload
            return MockStreamResponse(with_tools)
            
    mock_httpx_class.return_value = MockClientContext()
    
    req = ChatRequest(
        model="fake/model",
        messages=[Message(role="user", content="Ping. You must reply precisely with the word 'PONG'.")],
        stream=True
    )
    
    chunks_received = []
    # Offline = False initiates the injection of tools
    async for chunk in generate_chat_openrouter(req, offline_mode=False):
        if "data: " in chunk:
            chunks_received.append(chunk)
            
    # We should not leak the API error
    assert not any("OpenRouter API Error" in c for c in chunks_received), f"Fallback logic failed! Chunks dumped: {chunks_received}"
    
    # It must successfully recover and stream the answer
    assert any("PONG" in content.upper() for content in chunks_received), "Model failed to output PONG post-fallback."

@pytest.mark.asyncio
@patch("services.openrouter.httpx.AsyncClient")
async def test_openrouter_tool_context_retention(mock_httpx_class, api_key):
    """Verifies that text generated before a tool call (like <think> tags) is preserved when executing the tool."""
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
    
    from models.schemas import ChatRequest, Message
    from services.openrouter import generate_chat_openrouter
    
    second_request_payload = {}
    
    class MockStreamResponse:
        def __init__(self, is_second_pass):
            self.is_second_pass = is_second_pass
            self.status_code = 200
            
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        
        async def aread(self): return b''
            
        async def aiter_lines(self):
            if not self.is_second_pass:
                # First pass: emit some thought context, then a tool call
                yield 'data: {"choices":[{"delta":{"content":"<think>Let me search</think>\\n"}}]}'
                yield 'data: {"choices":[{"delta":{"tool_calls":[{"id":"call_123","function":{"name":"web_search","arguments":"{\\"query\\":\\"test\\"}"}}]}}]}'
                yield 'data: [DONE]'
            else:
                # Second pass: emit final answer
                yield 'data: {"choices":[{"delta":{"content":"Search completed."}}]}'
                yield 'data: [DONE]'

    class MockClientContext:
        def __init__(self):
            self.pass_count = 0
            
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): pass
        
        def stream(self, method, url, **kwargs):
            self.pass_count += 1
            payload = kwargs.get('json', {})
            if self.pass_count == 2:
                # Capture the payload of the second request to verify history preservation
                nonlocal second_request_payload
                second_request_payload = payload
            return MockStreamResponse(is_second_pass=(self.pass_count == 2))
            
    mock_httpx_class.return_value = MockClientContext()
    
    req = ChatRequest(
        model="fake/model",
        messages=[Message(role="user", content="Search for test")]
    )
    
    chunks = [c async for c in generate_chat_openrouter(req, offline_mode=False)]
    
    # Check that second_request_payload captured the messages properly
    assert "messages" in second_request_payload, "Second request was never made!"
    messages = second_request_payload["messages"]
    
    # We expect: system, user, assistant (with tool calls AND content), tool result
    assistant_msg = next((m for m in messages if m["role"] == "assistant" and "tool_calls" in m), None)
    assert assistant_msg is not None, "Assistant tool call message was not appended to history."
    assert "content" in assistant_msg, "Assistant message is missing 'content' key completely."
    
    # CRITICAL: Verify the <think> context wasn't wiped!
    assert assistant_msg["content"] == "<think>Let me search</think>\n", f"Context was lost! Got content: {assistant_msg['content']}"

def test_duckduckgo_library_health():
    """Explicitly tests the ddgs library to ensure its API hasn't changed and it doesn't silently return empty arrays."""
    from ddgs import DDGS
    try:
        results = list(DDGS().text('apple stock price', max_results=2))
        assert isinstance(results, list), "DDGS text() did not return a list/iterable of results."
        assert len(results) > 0, "DDGS silently returned an empty list. The upstream library might be broken again!"
        assert "title" in results[0] and "href" in results[0], "DDGS result format changed!"
    except Exception as e:
        pytest.fail(f"DuckDuckGo integration natively threw an error: {e}")
