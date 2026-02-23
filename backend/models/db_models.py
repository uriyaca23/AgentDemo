from sqlalchemy import Column, String, JSON, DateTime
import uuid
import datetime
from database import Base

class ConversationDB(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    messages = Column(JSON, default=list)
