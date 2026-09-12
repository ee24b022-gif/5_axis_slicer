from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from enums import JobMode, JobStatus, UserRole
from models import Job, MachineProfile, Mesh, User

VALID_CONTRACT = {
    "calibration_revision": 1,
    "kinematic_convention": "AC_TABLE",
    "units": "mm",
    "axis_names": ["X", "Y", "Z", "A", "C"],
    "axis_directions": {"X": 1, "Y": 1, "Z": 1, "A": 1, "C": 1},
    "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0, "C": 0.0},
    "command_templates": {"linear": "G1 X{X} Y{Y} Z{Z}"},
}

def test_enum_save():
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    user = User(username="u1", email="e1", role=UserRole.USER, hashed_password="pwd")
    db.add(user)
    db.commit()

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="h1",
        storage_uri="s1",
        size_bytes=1,
        triangle_count=1,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    
    profile = MachineProfile(
        name="Test Profile",
        revision=1,
        dialect="MARLIN",
        contract=VALID_CONTRACT,
        limits={"ranges": {"X": [0.0, 200.0], "Y": [0.0, 200.0], "Z": [0.0, 200.0]}},
        author_id=user.id
    )
    
    db.add_all([mesh, profile])
    db.commit()

    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1",
        input_hash="h1",
        status=JobStatus.COMPLETE,
        completed_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()

    saved_job = db.execute(job.__table__.select()).first()
    assert saved_job is not None