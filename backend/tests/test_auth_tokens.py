import pytest
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError

from models import User, APIKey, RefreshToken
from database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from enums import UserRole

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_api_key_creation(session):
    user = User(
        username="api_user",
        email="api@example.com",
        role=UserRole.USER,
        hashed_password="hashed_password"
    )
    session.add(user)
    session.commit()
    
    api_key = APIKey(
        user_id=user.id,
        key_hash="fake_hash_value",
        prefix="sk-fake",
        scopes=["read:jobs", "write:jobs"],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        description="Test API Key"
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    
    assert api_key.id is not None
    assert api_key.user_id == user.id
    assert api_key.key_hash == "fake_hash_value"
    assert api_key.prefix == "sk-fake"
    assert "read:jobs" in api_key.scopes
    assert api_key.revoked_at is None
    assert api_key.created_at is not None

def test_api_key_cascade_delete(session):
    user = User(
        username="api_user2",
        email="api2@example.com",
        role=UserRole.USER,
        hashed_password="hashed_password"
    )
    session.add(user)
    session.commit()
    
    api_key = APIKey(
        user_id=user.id,
        key_hash="fake_hash_value_2",
        prefix="sk-fake2"
    )
    session.add(api_key)
    session.commit()
    
    # Delete user and verify cascade
    session.delete(user)
    session.commit()
    
    key_count = session.query(APIKey).filter_by(key_hash="fake_hash_value_2").count()
    assert key_count == 0

def test_refresh_token_rotation(session):
    user = User(
        username="token_user",
        email="token@example.com",
        role=UserRole.USER,
        hashed_password="hashed_password"
    )
    session.add(user)
    session.commit()
    
    # Create original token
    token1 = RefreshToken(
        user_id=user.id,
        token_hash="hash1",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    session.add(token1)
    session.commit()
    
    # Rotate token
    token2 = RefreshToken(
        user_id=user.id,
        token_hash="hash2",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    session.add(token2)
    session.commit()
    
    # Link rotation
    token1.replaced_by_id = token2.id
    token1.revoked_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(token1)
    
    assert token1.replaced_by_id == token2.id
    assert token1.replaced_by.token_hash == "hash2"
    assert token1.revoked_at is not None
