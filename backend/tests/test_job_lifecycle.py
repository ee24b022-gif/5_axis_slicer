import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Job, User, Mesh, MachineProfile
from enums import JobStatus, JobMode, UserRole
from job_lifecycle import JobLifecycle, InvalidTransitionError

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # Create required foreign key entities
    user = User(id=uuid.uuid4(), username="testuser", email="test@test.com", hashed_password="hash", role=UserRole.USER)
    mesh = Mesh(
        id=uuid.uuid4(),
        uploader_id=user.id,
        content_hash="hash",
        storage_uri="s3://test",
        size_bytes=100,
        triangle_count=10,
        bound_min_x=0, bound_min_y=0, bound_min_z=0,
        bound_max_x=0, bound_max_y=0, bound_max_z=0
    )
    from enums import RotationConvention
    contract = {
        "calibration_revision": 1,
        "kinematic_convention": RotationConvention.BC_TABLE.value,
        "units": "mm",
        "axis_names": ["X", "Y", "Z"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0},
        "command_templates": {}
    }
    limits = {
        "ranges": {"X": [0.0, 100.0], "Y": [0.0, 100.0], "Z": [0.0, 100.0]}
    }
    machine = MachineProfile(
        id=uuid.uuid4(),
        name="Test Machine",
        revision=1,
        dialect="marlin",
        contract=contract,
        limits=limits,
        author_id=user.id
    )
    
    session.add_all([user, mesh, machine])
    session.commit()
    
    yield session
    session.close()

def create_pending_job(session):
    user = session.query(User).first()
    mesh = session.query(Mesh).first()
    machine = session.query(MachineProfile).first()
    
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=machine.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash123",
        status=JobStatus.PENDING
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job

def test_valid_transitions(db_session):
    job = create_pending_job(db_session)
    assert job.status == JobStatus.PENDING
    assert job.started_at is None
    
    # Start job
    job = JobLifecycle.start_job(db_session, job)
    assert job.status == JobStatus.RUNNING
    assert job.started_at is not None
    assert job.completed_at is None
    
    # Complete job
    job = JobLifecycle.complete_job(db_session, job)
    assert job.status == JobStatus.COMPLETE
    assert job.completed_at is not None
    assert job.progress == 1.0

def test_invalid_transition_rejected(db_session):
    job = create_pending_job(db_session)
    JobLifecycle.start_job(db_session, job)
    JobLifecycle.complete_job(db_session, job)
    
    # Attempting to start a completed job should fail
    with pytest.raises(InvalidTransitionError):
        JobLifecycle.start_job(db_session, job)

def test_idempotent_terminal_state(db_session):
    job = create_pending_job(db_session)
    JobLifecycle.start_job(db_session, job)
    JobLifecycle.fail_job(db_session, job)
    
    assert job.status == JobStatus.FAILED
    
    # Duplicate worker completion message simulating failing the same job again
    job = JobLifecycle.fail_job(db_session, job)
    
    # Should not raise an error, just gracefully no-op
    assert job.status == JobStatus.FAILED
