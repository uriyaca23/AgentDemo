from sqlalchemy.orm import Session
from models.db_models import Conversation, Base
from database import engine
import uuid

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

def get_conversations(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Conversation).order_by(Conversation.created_at.desc()).offset(skip).limit(limit).all()

def get_conversation(db: Session, conversation_id: str):
    return db.query(Conversation).filter(Conversation.id == conversation_id).first()

def create_conversation(db: Session, title: str, messages: list):
    db_conv = Conversation(id=str(uuid.uuid4()), title=title, messages=messages)
    db.add(db_conv)
    db.commit()
    db.refresh(db_conv)
    return db_conv

def update_conversation(db: Session, conversation_id: str, messages: list):
    db_conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if db_conv:
        db_conv.messages = messages
        db.commit()
        db.refresh(db_conv)
    return db_conv
