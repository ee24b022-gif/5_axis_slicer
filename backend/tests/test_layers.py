import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import User, Job, Layer, Mesh, MachineProfile
from enums import UserRole, JobMode, MeshFormat

@pytest.fixture
def session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_layer_creation_defaults(session):
    user = User(
        username="layeruser",
        email="layer@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id, content_hash="hash_l1", storage_uri="s",
        size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    profile = MachineProfile(name="N3", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h")

    user.jobs.append(job)
    
    layer = Layer(
        layer_idx=1,
        z_height=0.2,
        thickness=0.2
    )
    job.layers.append(layer)
    
    session.add(user)
    session.commit()
    
    session.refresh(layer)
    
    assert layer.id is not None
    assert layer.job_id == job.id
    assert layer.job == job
    assert layer.is_planar is True
    assert layer.is_support is False
    assert layer.gcode_offset is None
    assert layer.created_at is not None
    # No soft delete fields
    assert not hasattr(layer, 'is_deleted')

def test_layer_cascade_delete(session):
    user = User(
        username="deluser2",
        email="del2@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id, content_hash="hash_l2", storage_uri="s",
        size_bytes=1, triangle_count=1, bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=1.0, bound_max_y=1.0, bound_max_z=1.0
    )
    profile = MachineProfile(name="N4", revision=1, dialect="d", contract={}, limits={}, author_id=user.id)
    session.add_all([mesh, profile])
    session.commit()
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="h")

    layer = Layer(
        layer_idx=1,
        z_height=0.2,
        thickness=0.2
    )
    job.layers.append(layer)
    user.jobs.append(job)
    
    session.add(user)
    session.commit()
    
    layer_id = layer.id
    
    # Delete the job (cascade should delete layer)
    session.delete(job)
    session.commit()
    
    deleted_layer = session.query(Layer).filter_by(id=layer_id).first()
    assert deleted_layer is None
