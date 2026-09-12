import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from models import User, Mesh, MachineProfile, Job, Chunk, Diagnostic
from enums import JobMode, JobStatus, ChunkValidity, DiagnosticSeverity, DiagnosticStatus, JobStage
from repositories import JobRepository, ChunkRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

@pytest.fixture
def mock_setup_data(session: Session):
    user = User(username="test_cp", email="test_cp@example.com", hashed_password="hash")
    session.add(user)
    session.flush()
    
    mesh = Mesh(
        uploader_id=user.id,
        content_hash="hash",
        storage_uri="s3://bucket/test.stl",
        size_bytes=100,
        triangle_count=100,
        bound_min_x=0.0,
        bound_min_y=0.0,
        bound_min_z=0.0,
        bound_max_x=10.0,
        bound_max_y=10.0,
        bound_max_z=10.0
    )
    session.add(mesh)
    
    mp = MachineProfile(
        name="Test Profile",
        revision=1,
        dialect="Marlin",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}},
        author_id=user.id
    )
    session.add(mp)
    session.flush()
    
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.INDEXED_MULTIDIRECTIONAL,
        settings={"layer_height": 0.2},
        engine_revision="1.0",
        input_hash="hash",
        status=JobStatus.PENDING
    )
    session.add(job)
    session.flush()
    
    chunk = Chunk(
        job_id=job.id,
        chunk_idx=0,
        source_plane={},
        transform_matrix=[1.0] * 16,
        layer_idx_min=0,
        layer_idx_max=100,
        min_z=0.0,
        max_z=10.0,
        validity=ChunkValidity.PENDING,
        storage_key="test_key",
        triangle_count=0
    )
    session.add(chunk)
    session.flush()
    
    return job, chunk

def test_chunk_checkpointing(session: Session, mock_setup_data):
    job, chunk = mock_setup_data
    repo = ChunkRepository(session)
    
    diag = Diagnostic(
        stage=JobStage.SECTIONING,
        severity=DiagnosticSeverity.ERROR,
        status=DiagnosticStatus.FAIL,
        code="INTERSECTION_FAILED",
        message="Intersection failed at layer 42"
    )
    
    updated_chunk = repo.update_chunk_checkpoint(
        chunk_id=chunk.id,
        validity=ChunkValidity.PARTIAL,
        last_completed_layer=42,
        diagnostics=[diag]
    )
    
    assert updated_chunk is not None
    assert updated_chunk.validity == ChunkValidity.PARTIAL
    assert updated_chunk.last_completed_layer == 42
    
    # Assert diagnostic was flushed and bound
    assert len(updated_chunk.diagnostics) == 1
    assert updated_chunk.diagnostics[0].message == "Intersection failed at layer 42"
    assert updated_chunk.diagnostics[0].chunk_id == chunk.id
    assert updated_chunk.diagnostics[0].job_id == job.id

def test_job_partial_failure(session: Session, mock_setup_data):
    job, _ = mock_setup_data
    repo = JobRepository(session)
    
    checkpoint_data = {"last_chunk": 0}
    
    updated_job = repo.update_job_progress(
        job_id=job.id,
        progress=0.45,
        status=JobStatus.FAILED,
        checkpoint_data=checkpoint_data
    )
    
    assert updated_job is not None
    assert updated_job.progress == 0.45
    assert updated_job.status == JobStatus.FAILED
    assert updated_job.checkpoint_data == checkpoint_data
