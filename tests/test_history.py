import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))
from models import db_models
from services import history

# Use an in-memory SQLite database for test isolation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db_models.Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        db_models.Base.metadata.drop_all(bind=engine)

def test_create_and_get_conversation(db_session):
    """Test creating a conversation and retrieving it by ID."""
    messages = [{"role": "user", "content": "Hello"}]
    conv = history.create_conversation(db_session, "Test Title", messages)
    
    assert conv.id is not None
    assert conv.title == "Test Title"
    assert len(conv.messages) == 1
    
    fetched = history.get_conversation(db_session, conv.id)
    assert fetched is not None
    assert fetched.id == conv.id
    assert fetched.messages == messages

def test_update_conversation(db_session):
    """Test updating a conversation's messages."""
    messages = [{"role": "user", "content": "Hello"}]
    conv = history.create_conversation(db_session, "Test Title", messages)
    
    new_messages = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}]
    updated = history.update_conversation(db_session, conv.id, new_messages)
    
    assert updated.id == conv.id
    assert len(updated.messages) == 2
    assert updated.messages[1]["content"] == "Hi!"

def test_delete_conversation(db_session):
    """Test deleting a conversation."""
    conv = history.create_conversation(db_session, "To Delete", [])
    
    success = history.delete_conversation(db_session, conv.id)
    assert success is True
    
    fetched = history.get_conversation(db_session, conv.id)
    assert fetched is None

def test_get_conversations_pagination(db_session):
    """Test retrieving multiple conversations with limits and offsets."""
    for i in range(15):
        history.create_conversation(db_session, f"Conv {i}", [])
        
    convs = history.get_conversations(db_session, limit=10, offset=0)
    assert len(convs) == 10
    
    convs_page2 = history.get_conversations(db_session, limit=10, offset=5)
    assert len(convs_page2) == 10
