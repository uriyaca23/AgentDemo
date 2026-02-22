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

    # Handle conversation saving
    conv_id = request.conversation_id
    if not conv_id:
        first_content = ""
        if request.messages:
            first_content = extract_text(request.messages[0].content)
        title = first_content[:35] + ("..." if len(first_content) > 35 else "") if first_content else "New Chat"
        db_conv = history.create_conversation(db, title=title, messages=[m.model_dump() for m in request.messages])
        conv_id = db_conv.id
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
