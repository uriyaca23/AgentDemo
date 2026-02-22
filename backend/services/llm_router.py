from models.schemas import ChatRequest
from services.openrouter import generate_chat_openrouter
from services.internal_llm import generate_chat_internal
from sqlalchemy.orm import Session

def get_chat_generator(request: ChatRequest, offline_mode: bool, conv_id: str = None, db: Session = None):
    if request.model == "qwen2.5-vl-72b-instruct": # This ID corresponds strictly to the 'internal' provider we set
        return generate_chat_internal(request, offline_mode, conv_id, db)
    else:
        return generate_chat_openrouter(request, offline_mode, conv_id, db)
