"""
OpenRouter API Emulator
=======================
A FastAPI translation layer that wraps vLLM's OpenAI-compatible API
and presents it with an interface identical to OpenRouter's API.

This allows the backend to use the exact same code path for both
OpenRouter (external) and the internal vLLM deployment.

Endpoints:
  POST /api/v1/chat/completions  — Chat completions (streaming + non-streaming)
  GET  /api/v1/models            — List available models
  GET  /api/v1/auth/key          — Stub auth check (always returns 200)
"""

import os
import json
import time
import uuid
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

# ── Configuration ────────────────────────────────────────────────────────────
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:5000/v1")
EMULATOR_PORT = int(os.environ.get("EMULATOR_PORT", "8000"))

app = FastAPI(title="OpenRouter API Emulator", version="1.0.0")


# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "OpenRouter Emulator is running", "vllm_backend": VLLM_BASE_URL}


# ── Auth Stub ────────────────────────────────────────────────────────────────
@app.get("/api/v1/auth/key")
async def auth_key(request: Request):
    """
    Stub that mimics OpenRouter's GET /api/v1/auth/key.
    In an air-gapped environment there is no real auth — always returns 200.
    The response format matches what OpenRouter returns.
    """
    return JSONResponse(content={
        "data": {
            "label": "internal-emulator",
            "usage": 0,
            "limit": None,
            "is_free_tier": False,
            "rate_limit": {
                "requests": 1000,
                "interval": "10s"
            }
        }
    })


# ── Models ───────────────────────────────────────────────────────────────────
@app.get("/api/v1/models")
async def list_models(request: Request):
    """
    Proxies vLLM's /v1/models and reformats the response to match
    OpenRouter's model listing format.

    OpenRouter format:
    {
      "data": [
        {
          "id": "org/model-name",
          "name": "Model Display Name",
          "context_length": 128000,
          "pricing": {"prompt": "0", "completion": "0"},
          "architecture": {...},
          "top_provider": {...}
        }
      ]
    }
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{VLLM_BASE_URL}/models", timeout=10.0)
            if resp.status_code != 200:
                return JSONResponse(
                    content={"data": []},
                    status_code=resp.status_code
                )
            vllm_data = resp.json()
    except Exception as e:
        return JSONResponse(content={"data": [], "error": str(e)}, status_code=502)

    # Transform vLLM's OpenAI-format model list to OpenRouter format
    openrouter_models = []
    for model in vllm_data.get("data", []):
        model_id = model.get("id", "unknown")
        openrouter_models.append({
            "id": model_id,
            "name": model_id,
            "description": f"Locally served model via vLLM",
            "context_length": model.get("max_model_len", 128000),
            "pricing": {
                "prompt": "0",
                "completion": "0"
            },
            "architecture": {
                "modality": "text+image->text",
                "tokenizer": "Other",
                "instruct_type": "none"
            },
            "top_provider": {
                "max_completion_tokens": model.get("max_model_len", 128000),
                "is_moderated": False
            },
            "per_request_limits": None
        })

    return JSONResponse(content={"data": openrouter_models})


# ── Chat Completions ─────────────────────────────────────────────────────────
@app.post("/api/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Proxies chat completion requests to the vLLM backend.
    Translates between OpenRouter request/response format and vLLM's
    OpenAI-compatible format.

    Key differences handled:
    1. OpenRouter sends extra headers (HTTP-Referer, X-Title) — we ignore them
    2. OpenRouter wraps errors differently — we match their format
    3. OpenRouter includes 'id' field as 'gen-XXXX' — we ensure same prefix format
    4. Tool calling: vLLM supports OpenAI-style tools; we pass them through
    """
    body = await request.json()

    # Build the vLLM-compatible request payload
    vllm_payload = {
        "model": body.get("model"),
        "messages": body.get("messages", []),
        "stream": body.get("stream", False),
    }

    # Forward optional parameters that both OpenAI and OpenRouter support
    for key in [
        "temperature", "top_p", "max_tokens", "stop", "frequency_penalty",
        "presence_penalty", "seed", "tools", "tool_choice",
        "response_format", "logprobs", "top_logprobs", "n"
    ]:
        if key in body:
            vllm_payload[key] = body[key]

    is_streaming = body.get("stream", False)

    try:
        if is_streaming:
            return StreamingResponse(
                _proxy_streaming(vllm_payload),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Request-Id": f"gen-{uuid.uuid4().hex[:16]}"
                }
            )
        else:
            return await _proxy_non_streaming(vllm_payload)

    except httpx.ConnectError:
        return JSONResponse(
            content={
                "error": {
                    "message": "vLLM backend is not available. Ensure the model server is running.",
                    "code": 502
                }
            },
            status_code=502
        )
    except Exception as e:
        return JSONResponse(
            content={
                "error": {
                    "message": str(e),
                    "code": 500
                }
            },
            status_code=500
        )


async def _proxy_streaming(vllm_payload: dict):
    """
    Proxies a streaming request to vLLM and translates each SSE chunk
    to match OpenRouter's format exactly.

    OpenRouter SSE format:
      data: {"id":"gen-xxx","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}],"model":"...","created":...}
      ...
      data: [DONE]
    """
    generation_id = f"gen-{uuid.uuid4().hex[:16]}"
    created_ts = int(time.time())

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{VLLM_BASE_URL}/chat/completions",
            json=vllm_payload,
            timeout=120.0
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                error_text = error_body.decode("utf-8", errors="replace")
                # Match OpenRouter's error format in SSE
                error_chunk = {
                    "error": {
                        "message": error_text,
                        "code": response.status_code
                    }
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"
                return

            async for line in response.aiter_lines():
                if not line:
                    continue

                if line.strip() == "data: [DONE]":
                    yield "data: [DONE]\n\n"
                    continue

                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        # Rewrite the chunk to match OpenRouter format
                        openrouter_chunk = _transform_streaming_chunk(
                            chunk, generation_id, created_ts, vllm_payload.get("model", "")
                        )
                        yield f"data: {json.dumps(openrouter_chunk)}\n\n"
                    except json.JSONDecodeError:
                        # Pass through unparseable lines as-is
                        yield line + "\n\n"


def _transform_streaming_chunk(
    vllm_chunk: dict,
    generation_id: str,
    created_ts: int,
    model: str
) -> dict:
    """
    Transform a vLLM/OpenAI-format streaming chunk to OpenRouter format.

    The formats are very similar. Main differences:
    - OpenRouter uses 'gen-XXXX' style IDs
    - OpenRouter always includes 'model' and 'created' in every chunk
    - OpenRouter may include usage stats in the final chunk
    """
    result = {
        "id": generation_id,
        "model": model,
        "created": created_ts,
        "object": "chat.completion.chunk",
    }

    # Copy choices as-is — the delta format is identical
    if "choices" in vllm_chunk:
        result["choices"] = vllm_chunk["choices"]

    # Forward usage if present (vLLM can include this in the last chunk)
    if "usage" in vllm_chunk and vllm_chunk["usage"]:
        result["usage"] = vllm_chunk["usage"]

    return result


async def _proxy_non_streaming(vllm_payload: dict) -> JSONResponse:
    """
    Proxies a non-streaming request to vLLM and translates the response
    to match OpenRouter format.
    """
    generation_id = f"gen-{uuid.uuid4().hex[:16]}"
    created_ts = int(time.time())

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{VLLM_BASE_URL}/chat/completions",
            json=vllm_payload,
            timeout=120.0
        )

        if response.status_code != 200:
            error_text = response.text
            return JSONResponse(
                content={
                    "error": {
                        "message": error_text,
                        "code": response.status_code
                    }
                },
                status_code=response.status_code
            )

        vllm_data = response.json()

    # Transform to OpenRouter format
    openrouter_response = {
        "id": generation_id,
        "model": vllm_payload.get("model", ""),
        "created": created_ts,
        "object": "chat.completion",
        "choices": vllm_data.get("choices", []),
        "usage": vllm_data.get("usage", {})
    }

    return JSONResponse(content=openrouter_response)


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=EMULATOR_PORT)
