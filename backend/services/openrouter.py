import os
import json
import httpx
from sqlalchemy.orm import Session
from services import history


def get_api_key():
    key_path = os.path.join(os.path.dirname(__file__), "../../api_key.txt")
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    return ""


async def generate_chat_openrouter(
    model: str,
    messages: list[dict],
    mode: str = "auto",
    offline_mode: bool = False,
    conv_id: str = None,
    db: Session = None,
):
    """
    Async generator that yields plain-text token strings for Gradio streaming.
    Handles SSE parsing from OpenRouter internally.
    """
    api_key = get_api_key()
    if not api_key:
        yield "⚠️ **Error:** `api_key.txt` not found or empty. Please create `api_key.txt` in the root directory with your OpenRouter API key."
        return

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:7860",
        "X-Title": "LLM Agent Hub",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": list(messages),  # copy
        "stream": True,
    }

    system_instruction = None

    if mode == "fast":
        payload["temperature"] = 0.7
        payload["max_tokens"] = 512
        system_instruction = {
            "role": "system",
            "content": "You are in FAST mode. Be highly concise and direct in your response.",
        }
    elif mode == "thinking":
        payload["temperature"] = 0.2
        system_instruction = {
            "role": "system",
            "content": (
                "You are in THINKING mode. Before answering, wrap your step-by-step "
                "reasoning inside <think>...</think> XML tags. After the closing </think> "
                "tag, provide your clear final answer. Always include your reasoning "
                "inside the think tags."
            ),
        }
    elif mode == "pro":
        payload["temperature"] = 0.5
        system_instruction = {
            "role": "system",
            "content": "You are in PRO mode. Provide an expert, nuanced, and highly detailed professional response.",
        }

    if offline_mode:
        offline_instruction = (
            "You are operating in an air-gapped, offline environment. "
            "You DO NOT have access to the internet. Do not formulate plans "
            "to search the web or provide fabricated internet links."
        )
        if system_instruction:
            system_instruction["content"] += "\n" + offline_instruction
        else:
            system_instruction = {"role": "system", "content": offline_instruction}

    if system_instruction:
        if payload["messages"] and payload["messages"][0].get("role") == "system":
            payload["messages"][0]["content"] += "\n" + system_instruction["content"]
        else:
            payload["messages"].insert(0, system_instruction)

    full_response = ""
    in_reasoning_block = False

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST", url, headers=headers, json=payload, timeout=60.0
            ) as response:
                if response.status_code != 200:
                    error_msg = await response.aread()
                    yield f"⚠️ OpenRouter API Error: {error_msg.decode()}"
                    return

                async for chunk in response.aiter_lines():
                    if chunk:
                        if chunk.startswith("data: ") and chunk != "data: [DONE]":
                            try:
                                data = json.loads(chunk[6:])
                                if data.get("choices") and len(data["choices"]) > 0:
                                    choice = data["choices"][0]
                                    # Handle reasoning_content for thinking models (e.g. DeepSeek R1)
                                    reasoning = choice.get("delta", {}).get(
                                        "reasoning_content", ""
                                    ) or choice.get("delta", {}).get("reasoning", "")
                                    if reasoning:
                                        if not in_reasoning_block:
                                            token = "<think>"
                                            in_reasoning_block = True
                                            full_response += token
                                            yield token
                                        full_response += reasoning
                                        yield reasoning

                                    delta = choice.get("delta", {}).get("content", "")
                                    if delta:
                                        if in_reasoning_block:
                                            token = "</think>"
                                            in_reasoning_block = False
                                            full_response += token
                                            yield token
                                        full_response += delta
                                        yield delta

                                    if choice.get("finish_reason") and in_reasoning_block:
                                        token = "</think>"
                                        in_reasoning_block = False
                                        full_response += token
                                        yield token
                            except json.JSONDecodeError:
                                pass

            # Save the assistant response to the database
            if conv_id and db and full_response:
                db_conv = history.get_conversation(db, conv_id)
                if db_conv:
                    updated_msgs = db_conv.messages + [
                        {"role": "assistant", "content": full_response}
                    ]
                    history.update_conversation(db, conv_id, updated_msgs)

        except Exception as e:
            yield f"⚠️ Error: {str(e)}"
