import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column
from database import Base
from mixins import TimestampMixin, SoftDeleteMixin
import time
from datetime import timezone

# Dummy model for testing
class DummyModel(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'dummy_models'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_timestamp_defaults(session):
    dummy = DummyModel(name="test1")
    session.add(dummy)
    session.commit()
    session.refresh(dummy)

    assert dummy.created_at is not None
    assert dummy.updated_at is not None
    # They are evaluated separately, so allow a small delta
    assert abs((dummy.created_at - dummy.updated_at).total_seconds()) < 0.1
    assert dummy.created_at.tzinfo in (timezone.utc, None)

def test_timestamp_on_update(session):
    dummy = DummyModel(name="test2")
    session.add(dummy)
    session.commit()
    session.refresh(dummy)
    
    initial_updated_at = dummy.updated_at
    
    # ensure a tiny amount of time passes
    time.sleep(0.01)
    
    dummy.name = "test2_updated"
    session.commit()
    session.refresh(dummy)
    
    assert dummy.updated_at > initial_updated_at
    assert dummy.created_at < dummy.updated_at
    assert dummy.updated_at.tzinfo in (timezone.utc, None)

def test_soft_delete_defaults(session):
    dummy = DummyModel(name="test3")
    session.add(dummy)
    session.commit()
    session.refresh(dummy)
    
    assert dummy.is_deleted is False
    assert dummy.deleted_at is None
