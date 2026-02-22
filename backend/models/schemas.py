from pydantic import BaseModel
from typing import List, Optional, Literal, Union, Dict, Any

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: Union[str, List[Dict[str, Any]]]
    
class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    mode: Literal["auto", "fast", "thinking", "pro"] = "auto"
    conversation_id: Optional[str] = None

class ModelMetadata(BaseModel):
    id: str
    name: str
    provider: Literal["openrouter", "internal"]
    description: str
    cost_per_m: float
    context_length: int
    intelligence: int
    speed: int
