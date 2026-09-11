import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from database import Base
from models import User
from enums import UserRole

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_user_insertion(session):
    user = User(
        username="testuser",
        email="test@example.com",
        role=UserRole.USER,
        hashed_password="hashed_password_123"
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.role == UserRole.USER
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.is_deleted is False

def test_duplicate_username(session):
    user1 = User(
        username="duplicate_user",
        email="test1@example.com",
        hashed_password="pwd"
    )
    session.add(user1)
    session.commit()

    user2 = User(
        username="duplicate_user",
        email="test2@example.com",
        hashed_password="pwd"
    )
    session.add(user2)
    
    with pytest.raises(IntegrityError):
        session.commit()

def test_duplicate_email(session):
    user1 = User(
        username="user1",
        email="duplicate@example.com",
        hashed_password="pwd"
    )
    session.add(user1)
    session.commit()

    user2 = User(
        username="user2",
        email="duplicate@example.com",
        hashed_password="pwd"
    )
    session.add(user2)
    
    with pytest.raises(IntegrityError):
        session.commit()
