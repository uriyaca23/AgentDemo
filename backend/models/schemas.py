from pydantic import BaseModel
from typing import List, Optional, Any

class Message(BaseModel):
    role: str
    content: Any # Can be string or list of objects for multimodal

class ChatRequest(BaseModel):
    messages: List[Message]
    model: str
    mode: str = "auto"
    conversation_id: Optional[str] = None

class NetworkToggle(BaseModel):
    enabled: bool

class UnlockRequest(BaseModel):
    password: str

class LlmProviderToggle(BaseModel):
    provider: str  # "emulator" or "openrouter"
