from sqlalchemy import Column, String, JSON, DateTime
from database import Base
import datetime

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    messages = Column(JSON)
