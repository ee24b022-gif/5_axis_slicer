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
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}},
        author_id=user.id
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)

    assert profile.id is not None
    assert profile.name == "PocketNC V2-10"
    assert profile.revision == 1
    assert profile.dialect == "linuxcnc"
    assert profile.contract == {"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}}
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
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}},
        author_id=user.id
    )
    session.add(profile1)
    session.commit()

    profile2 = MachineProfile(
        name="PocketNC V2-10",
        revision=1,
        dialect="linuxcnc",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}},
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
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}},
        author_id=user.id
    )
    session.add(profile)
    session.commit()

    session.delete(user)
    session.commit()

    assert session.query(MachineProfile).count() == 0
