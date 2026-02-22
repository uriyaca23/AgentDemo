from services.openrouter import generate_chat_openrouter
from services.internal_llm import generate_chat_internal
from sqlalchemy.orm import Session


def get_chat_generator(
    model: str,
    messages: list[dict],
    mode: str = "auto",
    offline_mode: bool = False,
    conv_id: str = None,
    db: Session = None,
):
    """
    Routes to the correct LLM backend generator.
    Returns an async generator that yields plain text tokens.
    """
    if model == "qwen2.5-vl-72b-instruct":
        return generate_chat_internal(model, messages, mode, offline_mode, conv_id, db)
    else:
        return generate_chat_openrouter(model, messages, mode, offline_mode, conv_id, db)
