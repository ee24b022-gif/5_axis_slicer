import pytest
from sqlalchemy.exc import IntegrityError
from models import User, Mesh, MachineProfile, Job
from enums import UserRole, MeshFormat, JobMode, JobStatus
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

def test_job_creation(session):
    user = User(
        username="job_creator",
        email="creator@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="mesh_hash",
        storage_uri="s3://bucket/mesh.stl",
        format=MeshFormat.STL_BINARY,
        size_bytes=1024,
        triangle_count=50,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh)
    
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

    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        settings={"stepover": 0.5},
        engine_revision="v1.0.0",
        input_hash="hash_repro"
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    assert job.id is not None
    assert job.status == JobStatus.PENDING
    assert job.creator.username == "job_creator"
    assert job.mesh.content_hash == "mesh_hash"
    assert job.machine_profile.name == "PocketNC V2-10"

def test_job_terminal_status_constraint(session):
    user = User(
        username="job_creator_2",
        email="creator2@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="mesh_hash_2",
        storage_uri="s3://bucket/mesh2.stl",
        size_bytes=1024, triangle_count=50,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    profile = MachineProfile(
        name="PocketNC V2-10", revision=2, dialect="linuxcnc",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}}, limits={"ranges": {"X": (0, 300)}}, author_id=user.id
    )
    session.add_all([mesh, profile])
    session.commit()

    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="v1.0.0",
        input_hash="hash_repro_2",
        status=JobStatus.COMPLETE,
        completed_at=None
    )
    session.add(job)
    
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

def test_job_restrict_deletion(session):
    user = User(
        username="job_creator_3",
        email="creator3@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="mesh_hash_3",
        storage_uri="s3://bucket/mesh3.stl",
        size_bytes=1024, triangle_count=50,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    profile = MachineProfile(
        name="PocketNC V2-10", revision=3, dialect="linuxcnc",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}}, limits={"ranges": {"X": (0, 300)}}, author_id=user.id
    )
    session.add_all([mesh, profile])
    session.commit()

    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="v1.0.0",
        input_hash="hash_repro_3"
    )
    session.add(job)
    session.commit()

    session.delete(profile)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
