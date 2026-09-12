import pytest
from fastapi.testclient import TestClient
from main import app
import trimesh
from io import BytesIO
import uuid
import os
from database import engine, Base, SessionLocal
from dependencies import get_current_actor, Actor
from models import User

@pytest.fixture(scope="module")
def default_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="test_uploader").first()
    if not user:
        user = User(username="test_uploader", email="test_upload@example.com", hashed_password="pw", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@pytest.fixture(autouse=True)
def override_auth(default_user):
    actor = Actor(
        actor_type="USER",
        user_id=default_user.id,
        key_id=None,
        scopes=["*"],
        user=default_user
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    yield
    app.dependency_overrides.pop(get_current_actor, None)

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    db.execute(Base.metadata.tables['meshes'].delete())
    db.commit()
    db.close()

def create_valid_mesh_bytes():
    mesh = trimesh.creation.box((10, 10, 10))
    f = BytesIO()
    mesh.export(f, file_type='stl')
    return f.getvalue()

def test_get_mesh_metadata_success():
    file_bytes = create_valid_mesh_bytes()
    # Upload the mesh
    upload_resp = client.post(
        "/meshes",
        files={"file": ("test.stl", file_bytes, "application/octet-stream")}
    )
    assert upload_resp.status_code == 200
    mesh_id = upload_resp.json()["id"]
    mesh_hash = upload_resp.json()["hash"]
    
    # Retrieve the metadata
    metadata_resp = client.get(f"/meshes/{mesh_id}")
    assert metadata_resp.status_code == 200
    
    data = metadata_resp.json()
    assert data["id"] == mesh_id
    assert data["content_hash"] == mesh_hash
    assert data["format"] == "stl_binary"
    assert data["triangle_count"] > 0
    assert "bound_min_x" in data
    assert "bound_max_x" in data

def test_get_mesh_metadata_not_found():
    random_uuid = str(uuid.uuid4())
    metadata_resp = client.get(f"/meshes/{random_uuid}")
    assert metadata_resp.status_code == 404
    assert metadata_resp.json()["detail"] == "Mesh not found"
