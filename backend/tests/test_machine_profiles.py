import pytest
from sqlalchemy.exc import IntegrityError
from models import User, MachineProfile
from enums import UserRole
from database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_machine_profile_creation(session):
    user = User(
        username="author_user",
        email="author@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    profile = MachineProfile(
        name="PocketNC V2-10",
        revision=1,
        dialect="linuxcnc",
        contract={"axis": "5"},
        limits={"max_speed": 100},
        author_id=user.id
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)

    assert profile.id is not None
    assert profile.name == "PocketNC V2-10"
    assert profile.revision == 1
    assert profile.dialect == "linuxcnc"
    assert profile.contract == {"axis": "5"}
    assert profile.is_active is True
    assert profile.author.username == "author_user"

def test_machine_profile_unique_constraint(session):
    user = User(
        username="author_user_2",
        email="author2@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    profile1 = MachineProfile(
        name="PocketNC V2-10",
        revision=1,
        dialect="linuxcnc",
        contract={"axis": "5"},
        limits={"max_speed": 100},
        author_id=user.id
    )
    session.add(profile1)
    session.commit()

    profile2 = MachineProfile(
        name="PocketNC V2-10",
        revision=1,
        dialect="linuxcnc",
        contract={"axis": "5"},
        limits={"max_speed": 100},
        author_id=user.id
    )
    session.add(profile2)
    
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

def test_machine_profile_cascade_delete(session):
    user = User(
        username="author_user_3",
        email="author3@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    profile = MachineProfile(
        name="Test Machine",
        revision=1,
        dialect="marlin",
        contract={"axis": "3"},
        limits={"max_speed": 100},
        author_id=user.id
    )
    session.add(profile)
    session.commit()

    session.delete(user)
    session.commit()

    assert session.query(MachineProfile).count() == 0
