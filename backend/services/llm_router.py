from models.schemas import ChatRequest
from services.openrouter import generate_chat_openrouter
from services.internal_llm import generate_chat_internal
from services.image_gen import generate_image_stream
from sqlalchemy.orm import Session

def get_chat_generator(request: ChatRequest, offline_mode: bool, conv_id: str = None, db: Session = None):
    # Extract last user message to check for skills
    last_msg = request.messages[-1]
    text = ""
    if isinstance(last_msg.content, str):
        text = last_msg.content
    elif isinstance(last_msg.content, list):
        for item in last_msg.content:
            if item.get("type") == "text":
                text = item.get("text", "")
                break
                
    if text.startswith("@generate_image"):
        return generate_image_stream(request, offline_mode, conv_id, db)
        
    if request.model == "qwen2.5-vl-72b-instruct": # This ID corresponds strictly to the 'internal' provider we set
        return generate_chat_internal(request, offline_mode, conv_id, db)
    else:
        return generate_chat_openrouter(request, offline_mode, conv_id, db)
