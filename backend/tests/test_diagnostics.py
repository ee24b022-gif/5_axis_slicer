import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from database import Base
from models import User, Job, Chunk, Layer, Diagnostic, Mesh, MachineProfile
from enums import UserRole, JobMode, JobStatus, MeshFormat, JobStage, ChunkValidity, DiagnosticSeverity, DiagnosticStatus
from datetime import datetime, timezone
import uuid

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def setup_entities(session):
    user = User(username="diag_user", email="diag@test.com", role=UserRole.USER, hashed_password="pw")
    session.add(user)
    session.commit()
    
    mesh = Mesh(
        uploader_id=user.id,
        storage_uri="s3://mesh",
        format=MeshFormat.STL_BINARY,
        size_bytes=1024,
        content_hash="hash1",
        triangle_count=100,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh)
    
    mp = MachineProfile(
        name="test_machine",
        revision=1,
        author_id=user.id,
        dialect="marlin",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}}
    )
    session.add(mp)
    session.commit()
    return user, mesh, mp

def test_diagnostic_creation_and_binding(session):
    """Verify diagnostic can be created and bound to job, chunk, and layer."""
    user, mesh, mp = setup_entities(session)

    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash"
    )
    session.add(job)
    session.commit()

    chunk = Chunk(
        job_id=job.id,
        chunk_idx=0,
        source_plane=[0,0,1,0],
        transform_matrix=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
        layer_idx_min=0,
        layer_idx_max=10,
        min_z=0.0,
        max_z=10.0,
        storage_key="test"
    )
    session.add(chunk)
    
    layer = Layer(
        job_id=job.id,
        layer_idx=0,
        z_height=0.2,
        thickness=0.2,
        gcode_offset=0
    )
    session.add(layer)
    session.commit()

    diag = Diagnostic(
        job_id=job.id,
        chunk_id=chunk.id,
        layer_id=layer.id,
        stage=JobStage.CHUNK_CONSTRUCTION,
        severity=DiagnosticSeverity.ERROR,
        status=DiagnosticStatus.FAIL,
        code="ERR_CHUNK_BOUNDS",
        message="Chunk bounds exceeded",
        details={"min_z": -1.0}
    )
    session.add(diag)
    session.commit()

    saved_diag = session.get(Diagnostic, diag.id)
    assert saved_diag is not None
    assert saved_diag.stage == JobStage.CHUNK_CONSTRUCTION
    assert saved_diag.severity == DiagnosticSeverity.ERROR
    assert saved_diag.details["min_z"] == -1.0
    
    # Check relationships
    assert saved_diag.job.id == job.id
    assert saved_diag.chunk.id == chunk.id
    assert saved_diag.layer.id == layer.id

    # Check backref
    assert len(job.diagnostics) == 1
    assert job.diagnostics[0].id == diag.id

def test_cross_job_integrity_failure_orm(session):
    """Test that ORM validation blocks assigning a chunk from a different job."""
    user, mesh, mp = setup_entities(session)

    job1 = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=mp.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1.0", input_hash="hash")
    job2 = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=mp.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1.0", input_hash="hash")
    session.add_all([job1, job2])
    session.commit()

    chunk_job2 = Chunk(
        job_id=job2.id,
        chunk_idx=0,
        source_plane=[0,0,1,0],
        transform_matrix=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
        layer_idx_min=0,
        layer_idx_max=10,
        min_z=0.0,
        max_z=10.0,
        storage_key="test2"
    )
    session.add(chunk_job2)
    session.commit()

    # Create diagnostic for job1 but try to link chunk_job2
    with pytest.raises(ValueError, match="Diagnostic chunk/layer belongs to a different job"):
        diag = Diagnostic(
            job_id=job1.id,
            chunk_id=chunk_job2.id,
            chunk=chunk_job2,
            stage=JobStage.CHUNK_CONSTRUCTION,
            severity=DiagnosticSeverity.ERROR,
            status=DiagnosticStatus.FAIL,
            code="TEST",
            message="Test"
        )
        session.add(diag)
        session.commit()

def test_diagnostic_cascade_delete(session):
    """Test that deleting a job deletes its diagnostics."""
    user, mesh, mp = setup_entities(session)

    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=mp.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1.0", input_hash="hash")
    session.add(job)
    session.commit()

    diag = Diagnostic(
        job_id=job.id,
        stage=JobStage.MESH_VALIDATION,
        severity=DiagnosticSeverity.INFO,
        status=DiagnosticStatus.PASS,
        code="INFO_001",
        message="Mesh is valid"
    )
    session.add(diag)
    session.commit()

    assert session.get(Diagnostic, diag.id) is not None

    session.delete(job)
    session.commit()

    assert session.get(Diagnostic, diag.id) is None
