from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from models.schemas import ChatRequest
from services import history, skills, openrouter
from settings import settings
import json

router = APIRouter(prefix="/chat", tags=["chat"])

@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    convs = history.get_conversations(db)
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in convs]

@router.get("/conversations/{conv_id}")
def load_conversation(conv_id: str, db: Session = Depends(get_db)):
    db_conv = history.get_conversation(db, conv_id)
    if not db_conv:
        return {"id": conv_id, "title": "New Chat", "messages": []}
    return {"id": db_conv.id, "title": db_conv.title, "messages": db_conv.messages}

@router.post("")
async def chat_completion(request: ChatRequest, db: Session = Depends(get_db)):
    offline_mode = not settings.get_network_enabled()
    
    def extract_text(content):
        if isinstance(content, str): return content
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text": return item.get("text", "")
        return ""

    # History saving
    conv_id = request.conversation_id
    if not conv_id:
        first_content = ""
        if request.messages:
            first_content = extract_text(request.messages[0].content).replace('\n', ' ').strip()
        title = first_content[:35] + ("..." if len(first_content) > 35 else "") if first_content else "New Chat"
        db_conv = history.create_conversation(db, title=title, messages=[m.model_dump() for m in request.messages])
        conv_id = db_conv.id
        
        if not offline_mode and first_content:
            import asyncio
            from services.openrouter import generate_title_background
            asyncio.create_task(generate_title_background(first_content, conv_id, request.model))
    else:
        db_conv = history.get_conversation(db, conv_id)
        if db_conv:
            updated_msgs = db_conv.messages + [request.messages[-1].model_dump()]
            history.update_conversation(db, conv_id, updated_msgs)

    # Agent Skills Interception
    text_input = extract_text(request.messages[-1].content)
    skill_generator = await skills.process_skills(text_input, db, conv_id)
    
    if skill_generator:
        generator = skill_generator
    else:
        # LLM Router
        if request.model == "qwen2.5-vl-72b-instruct":
            # Just fallback dummy stream for local missing model parity during tests
            async def fallback(): yield f"data: {json.dumps({'choices': [{'delta': {'content': 'Internal Model Offline.'}}]})}\n\n"
            generator = fallback()
        else:
            # We always route to OpenRouter. 
            # If offline_mode is true, OpenRouter will simply disable tools/web_search internally.
            generator = openrouter.generate_chat_openrouter(request, offline_mode, conv_id, db)
    
    return StreamingResponse(
        generator, 
        media_type="text/event-stream",
        headers={"x-conversation-id": conv_id}
    )
