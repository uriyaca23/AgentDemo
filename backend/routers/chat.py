from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.schemas import ChatRequest
from services import history
from services.llm_router import get_chat_generator
from settings import settings

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("")
async def chat_completion(request: ChatRequest, db: Session = Depends(get_db)):
    offline_mode = not settings.get_network_enabled()
    
    def extract_text(content):
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            for item in content:
                if item.get("type") == "text":
                    return item.get("text", "")
        return ""

    from fastapi import BackgroundTasks
    import httpx
    import json
    import os

    def generate_title_task(conv_id: str, first_msg: str):
        # We spawn a synchronous DB session just for this background task snippet
        # because the dependency injected `db` might close after the streaming request starts.
        # But this is simple enough to just request a fast title from OpenRouter
        # and open a local session.
        from database import SessionLocal
        from services.openrouter import get_api_key
        
        api_key = get_api_key()
        if not api_key: return

        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a title generator. Generate a concise 3-4 word title for a chat based on the user's first message. Do not use quotes or punctuation."},
                {"role": "user", "content": first_msg}
            ]
        }
        
        try:
            r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                           headers={"Authorization": f"Bearer {api_key}"},
                           json=payload, timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                new_title = data["choices"][0]["message"]["content"].strip(' ".,')
                with SessionLocal() as bg_db:
                    history.update_conversation_title(bg_db, conv_id, new_title)
        except Exception as e:
            print("Title generation failed:", e)

    # Handle conversation saving
    conv_id = request.conversation_id
    if not conv_id:
        first_content = ""
        if request.messages:
            first_content = extract_text(request.messages[0].content)
        title = first_content[:35] + ("..." if len(first_content) > 35 else "") if first_content else "New Chat"
        db_conv = history.create_conversation(db, title=title, messages=[m.model_dump() for m in request.messages])
        conv_id = db_conv.id
        
        from fastapi import BackgroundTasks
        # We need it injected if we used it properly, but to avoid changing endpoint signature
        # simply spawn a Thread or asyncio task. Since it's fastAPI, let's just 
        # use asyncio.create_task if we are inside async def, but this involves sync sqlalchemy.
        import asyncio
        import concurrent.futures
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, generate_title_task, conv_id, first_content)
    else:
        # Append user message to existing conversation
        db_conv = history.get_conversation(db, conv_id)
        if db_conv:
            updated_msgs = db_conv.messages + [request.messages[-1].model_dump()]
            history.update_conversation(db, conv_id, updated_msgs)

    # Pass the conversation ID to the generator so it can save the assistant's response later
    # (In a real app, this is tricky with streaming. A simpler approach is having the frontend 
    # send the full log back, or we yield a custom event stream). 
    # For now, we will return the generated conv_id as a Header.
    generator = get_chat_generator(request, offline_mode, conv_id, db)
    
    return StreamingResponse(
        generator, 
        media_type="text/event-stream",
        headers={"x-conversation-id": conv_id} # Inform the frontend
    )

class ConversationCreate(BaseModel):
    title: str
    messages: list

class ConversationUpdate(BaseModel):
    messages: list

@router.get("/conversations")
def read_conversations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return history.get_conversations(db, skip=skip, limit=limit)

@router.get("/conversations/{conversation_id}")
def read_conversation(conversation_id: str, db: Session = Depends(get_db)):
    return history.get_conversation(db, conversation_id=conversation_id)

@router.post("/conversations")
def create_conversation(data: ConversationCreate, db: Session = Depends(get_db)):
    return history.create_conversation(db, title=data.title, messages=data.messages)

@router.put("/conversations/{conversation_id}")
def update_conversation(conversation_id: str, data: ConversationUpdate, db: Session = Depends(get_db)):
    return history.update_conversation(db, conversation_id=conversation_id, messages=data.messages)
