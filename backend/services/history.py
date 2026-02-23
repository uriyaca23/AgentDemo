from sqlalchemy.orm import Session
from models import db_models
from typing import List, Dict

def get_conversations(db: Session, limit: int = 50, offset: int = 0):
    return db.query(db_models.ConversationDB).order_by(db_models.ConversationDB.created_at.desc()).offset(offset).limit(limit).all()

def get_conversation(db: Session, conv_id: str):
    return db.query(db_models.ConversationDB).filter(db_models.ConversationDB.id == conv_id).first()

def create_conversation(db: Session, title: str, messages: List[Dict]):
    db_conv = db_models.ConversationDB(title=title, messages=messages)
    db.add(db_conv)
    db.commit()
    db.refresh(db_conv)
    return db_conv

def update_conversation(db: Session, conv_id: str, messages: List[Dict]):
    db_conv = db.query(db_models.ConversationDB).filter(db_models.ConversationDB.id == conv_id).first()
    if db_conv:
        db_conv.messages = messages
        # ORM requires re-assignment for JSON mutation detection
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(db_conv, "messages")
        db.commit()
        db.refresh(db_conv)
    return db_conv

def update_conversation_title(db: Session, conv_id: str, title: str):
    db_conv = db.query(db_models.ConversationDB).filter(db_models.ConversationDB.id == conv_id).first()
    if db_conv:
        db_conv.title = title
        db.commit()
    return db_conv

def delete_conversation(db: Session, conv_id: str):
    db_conv = db.query(db_models.ConversationDB).filter(db_models.ConversationDB.id == conv_id).first()
    if db_conv:
        db.delete(db_conv)
        db.commit()
        return True
    return False
