import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from database import Base
from models import User, Job, Chunk, Mesh, MachineProfile
from enums import UserRole, JobMode, MeshFormat, ChunkValidity

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_chunk_creation_and_binding(session):
    user = User(
        username="chunkuser",
        email="chunk@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id, content_hash="hash_c3", storage_uri="s",
        size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    profile = MachineProfile(name="N3", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h")

    user.jobs.append(job)
    
    chunk = Chunk(
        chunk_idx=0,
        source_plane={"origin": [0,0,0], "normal": [0,0,1]},
        transform_matrix=[1.0, 0.0, 0.0, 0.0,
                          0.0, 1.0, 0.0, 0.0,
                          0.0, 0.0, 1.0, 0.0,
                          0.0, 0.0, 0.0, 1.0],
        layer_idx_min=0,
        layer_idx_max=100,
        min_z=0.0,
        max_z=10.5,
        storage_key="s3://chunks/job1/chunk1.bin"
    )
    job.chunks.append(chunk)
    
    session.add(user)
    session.commit()
    
    session.refresh(job)
    session.refresh(chunk)
    
    assert chunk.id is not None
    assert chunk.job_id == job.id
    assert chunk.job == job
    assert chunk.validity == ChunkValidity.PENDING
    assert chunk.triangle_count == 0
    assert chunk.created_at is not None
    assert not hasattr(chunk, 'is_deleted')

def test_chunk_duplicate_index_rejected(session):
    user = User(
        username="chunkuser_dup", email="chunkdup@example.com", role=UserRole.USER, hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(uploader_id=user.id, content_hash="hash_c4", storage_uri="s", size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0, bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0)
    profile = MachineProfile(name="N4", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h2")
    session.add(job)
    session.commit()

    chunk1 = Chunk(
        job_id=job.id, chunk_idx=1, source_plane={}, transform_matrix=[1.0]*16,
        layer_idx_min=0, layer_idx_max=10, min_z=0.0, max_z=1.0, storage_key="s1"
    )
    chunk2 = Chunk(
        job_id=job.id, chunk_idx=1, source_plane={}, transform_matrix=[1.0]*16,
        layer_idx_min=11, layer_idx_max=20, min_z=1.0, max_z=2.0, storage_key="s2"
    )
    session.add_all([chunk1, chunk2])
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

def test_chunk_transform_validation_fails(session):
    user = User(username="chunkuser_val", email="val@example.com", role=UserRole.USER, hashed_password="pwd")
    session.add(user)
    session.commit()
    mesh = Mesh(uploader_id=user.id, content_hash="hash_c5", storage_uri="s", size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0, bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0)
    profile = MachineProfile(name="N5", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h3")
    session.add(job)
    session.commit()

    with pytest.raises(ValueError, match="flat 16-element list"):
        Chunk(
            job_id=job.id, chunk_idx=1, source_plane={}, transform_matrix=[1.0, 2.0], # not 16
            layer_idx_min=0, layer_idx_max=10, min_z=0.0, max_z=1.0, storage_key="s1"
        )
    
    with pytest.raises(ValueError, match="Transform matrix elements must be numbers"):
        Chunk(
            job_id=job.id, chunk_idx=1, source_plane={}, transform_matrix=["string"]*16,
            layer_idx_min=0, layer_idx_max=10, min_z=0.0, max_z=1.0, storage_key="s1"
        )

def test_chunk_ordering_deterministic(session):
    user = User(username="chunkuser_ord", email="ord@example.com", role=UserRole.USER, hashed_password="pwd")
    session.add(user)
    session.commit()
    mesh = Mesh(uploader_id=user.id, content_hash="hash_c6", storage_uri="s", size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0, bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0)
    profile = MachineProfile(name="N6", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h4")
    session.add(job)
    session.commit()

    chunk3 = Chunk(job_id=job.id, chunk_idx=3, source_plane={}, transform_matrix=[1.0]*16, layer_idx_min=20, layer_idx_max=30, min_z=2.0, max_z=3.0, storage_key="s3")
    chunk1 = Chunk(job_id=job.id, chunk_idx=1, source_plane={}, transform_matrix=[1.0]*16, layer_idx_min=0, layer_idx_max=10, min_z=0.0, max_z=1.0, storage_key="s1")
    chunk2 = Chunk(job_id=job.id, chunk_idx=2, source_plane={}, transform_matrix=[1.0]*16, layer_idx_min=10, layer_idx_max=20, min_z=1.0, max_z=2.0, storage_key="s2")
    
    session.add_all([chunk3, chunk1, chunk2])
    session.commit()

    chunks = session.query(Chunk).filter_by(job_id=job.id).order_by(Chunk.chunk_idx).all()
    assert len(chunks) == 3
    assert chunks[0].chunk_idx == 1
    assert chunks[1].chunk_idx == 2
    assert chunks[2].chunk_idx == 3

def test_chunk_cascade_delete(session):
    user = User(
        username="deluser",
        email="del@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id, content_hash="hash_c2", storage_uri="s",
        size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    profile = MachineProfile(name="N2", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h")

    chunk = Chunk(
        chunk_idx=0,
        source_plane={},
        transform_matrix=[1.0]*16,
        layer_idx_min=0,
        layer_idx_max=10,
        min_z=0.0,
        max_z=1.0,
        storage_key="s3://del/chunk.bin"
    )
    job.chunks.append(chunk)
    user.jobs.append(job)
    
    session.add(user)
    session.commit()
    
    chunk_id = chunk.id
    
    session.delete(job)
    session.commit()
    
    deleted_chunk = session.query(Chunk).filter_by(id=chunk_id).first()
    assert deleted_chunk is None
