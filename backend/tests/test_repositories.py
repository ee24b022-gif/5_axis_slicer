import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from models import Base, User, Mesh, MachineProfile, Job, Chunk, Diagnostic, Export
from enums import UserRole, MeshFormat, JobMode, DiagnosticSeverity, DiagnosticStatus, JobStage, ExportStatus
from repositories import (
    UserRepository, 
    MeshRepository, 
    MachineProfileRepository, 
    JobRepository, 
    ChunkRepository,
    DiagnosticRepository,
    ExportRepository
)

from sqlalchemy import create_engine, event

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_user_repository_crud_and_rollback(session):
    repo = UserRepository(session)
    
    # Test Create
    user_data = {
        "username": "testuser",
        "email": "test@test.com",
        "role": UserRole.USER,
        "hashed_password": "pw"
    }
    user = repo.create(user_data)
    session.commit()
    
    assert user.id is not None
    assert user.username == "testuser"
    
    # Test Idempotency / IntegrityError (Duplicate Username)
    with pytest.raises(IntegrityError):
        repo.create({
            "username": "testuser",  # Duplicate
            "email": "test2@test.com",
            "role": UserRole.USER,
            "hashed_password": "pw"
        })
    # Repo automatically rolls back on IntegrityError
    
    # Ensure session is usable again after rollback
    user2 = repo.create({
        "username": "testuser2",
        "email": "test2@test.com",
        "role": UserRole.USER,
        "hashed_password": "pw"
    })
    session.commit()
    assert user2.id is not None

def test_chunk_repository_ordering(session):
    user_repo = UserRepository(session)
    mesh_repo = MeshRepository(session)
    profile_repo = MachineProfileRepository(session)
    job_repo = JobRepository(session)
    chunk_repo = ChunkRepository(session)
    
    # Setup dependencies
    u = user_repo.create({"username": "u1", "email": "e1@t.com", "role": UserRole.USER, "hashed_password": "pw"})
    m = mesh_repo.create({
        "uploader_id": u.id, "storage_uri": "s3", "format": MeshFormat.STL_BINARY,
        "size_bytes": 1, "content_hash": "h1", "triangle_count": 1,
        "bound_min_x": 0.0, "bound_min_y": 0.0, "bound_min_z": 0.0,
        "bound_max_x": 1.0, "bound_max_y": 1.0, "bound_max_z": 1.0
    })
    p = profile_repo.create({"name": "p1", "revision": 1, "dialect": "d1", "contract": {"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}}, "limits": {"ranges": {"X": (0, 300)}}, "author_id": u.id})
    j = job_repo.create({
        "creator_id": u.id, "mesh_id": m.id, "machine_profile_id": p.id,
        "mode": JobMode.THREE_AXIS, "settings": {}, "engine_revision": "1", "input_hash": "h1"
    })
    session.commit()
    
    # Insert chunks out of order
    c2 = chunk_repo.create({"job_id": j.id, "chunk_idx": 2, "source_plane": {}, "transform_matrix": [1.0]*16, "layer_idx_min": 1, "layer_idx_max": 2, "min_z": 1.0, "max_z": 2.0, "triangle_count": 1, "storage_key": "k2"})
    c1 = chunk_repo.create({"job_id": j.id, "chunk_idx": 1, "source_plane": {}, "transform_matrix": [1.0]*16, "layer_idx_min": 0, "layer_idx_max": 1, "min_z": 0.0, "max_z": 1.0, "triangle_count": 1, "storage_key": "k1"})
    session.commit()
    
    # Query ordered chunks
    chunks = chunk_repo.get_chunks_for_job(j.id)
    assert len(chunks) == 2
    assert chunks[0].chunk_idx == 1
    assert chunks[1].chunk_idx == 2

def test_foreign_key_failures(session):
    job_repo = JobRepository(session)
    
    # Attempt to create a job with non-existent user, mesh, and profile
    with pytest.raises(IntegrityError):
        job_repo.create({
            "creator_id": uuid.uuid4(), 
            "mesh_id": uuid.uuid4(), 
            "machine_profile_id": uuid.uuid4(),
            "mode": JobMode.THREE_AXIS, 
            "settings": {}, 
            "engine_revision": "1", 
            "input_hash": "h1"
        })
    # Repo automatically rolls back on IntegrityError
    
    # Session is clean
    user_repo = UserRepository(session)
    u = user_repo.create({"username": "clean", "email": "clean@t.com", "role": UserRole.USER, "hashed_password": "pw"})
    assert u.id is not None
