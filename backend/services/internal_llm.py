import json
import httpx
from sqlalchemy.orm import Session
from services import history


async def generate_chat_internal(
    model: str,
    messages: list[dict],
    mode: str = "auto",
    offline_mode: bool = False,
    conv_id: str = None,
    db: Session = None,
):
    """
    Async generator that yields plain-text token strings for Gradio streaming.
    Connects to the local vLLM OpenAI-compatible API.
    """
    url = "http://localhost:8000/v1/chat/completions"

    payload = {
        "model": "Qwen/Qwen2.5-VL-72B-Instruct-AWQ",
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
            "You DO NOT have access to the internet."
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

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST", url, json=payload, timeout=60.0
            ) as response:
                if response.status_code != 200:
                    error_msg = await response.aread()
                    yield f"⚠️ Internal LLM Error: {error_msg.decode()}"
                    return

                async for chunk in response.aiter_lines():
                    if chunk:
                        if chunk.startswith("data: ") and chunk != "data: [DONE]":
                            try:
                                data = json.loads(chunk[6:])
                                if data.get("choices") and len(data["choices"]) > 0:
                                    delta = (
                                        data["choices"][0]
                                        .get("delta", {})
                                        .get("content", "")
                                    )
                                    if delta:
                                        full_response += delta
                                        yield delta
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
            error_message = f"⚠️ Failed to connect to internal model. Make sure vLLM is running. ({str(e)})"
            yield error_message
