import pytest
from sqlalchemy.exc import IntegrityError
from models import User, Mesh
from enums import UserRole, MeshFormat
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

def test_mesh_creation_and_binding(session):
    user = User(
        username="mesh_user",
        email="mesh@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="mesh_hash_abc123",
        storage_uri="s3://bucket/mesh.stl",
        format=MeshFormat.STL_BINARY,
        size_bytes=1024,
        triangle_count=50,
        bound_min_x=0.0,
        bound_min_y=0.0,
        bound_min_z=0.0,
        bound_max_x=10.0,
        bound_max_y=10.0,
        bound_max_z=10.0
    )
    session.add(mesh)
    session.commit()
    session.refresh(mesh)

    assert mesh.id is not None
    assert mesh.uploader_id == user.id
    assert mesh.content_hash == "mesh_hash_abc123"
    assert mesh.size_bytes == 1024
    assert mesh.uploader.username == "mesh_user"

def test_mesh_deduplication_constraint(session):
    user = User(
        username="mesh_user_2",
        email="mesh2@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh1 = Mesh(
        uploader_id=user.id,
        content_hash="duplicate_hash",
        storage_uri="s3://bucket/mesh1.stl",
        size_bytes=1024,
        triangle_count=50,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh1)
    session.commit()

    mesh2 = Mesh(
        uploader_id=user.id,
        content_hash="duplicate_hash",
        storage_uri="s3://bucket/mesh2.stl",
        size_bytes=1024,
        triangle_count=50,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh2)
    
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

def test_mesh_cascade_delete(session):
    user = User(
        username="mesh_user_3",
        email="mesh3@example.com",
        role=UserRole.USER,
        hashed_password="pwd"
    )
    session.add(user)
    session.commit()

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="hash_3",
        storage_uri="s3://bucket/mesh3.stl",
        size_bytes=1024,
        triangle_count=50,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    session.add(mesh)
    session.commit()

    session.delete(user)
    session.commit()

    assert session.query(Mesh).count() == 0
