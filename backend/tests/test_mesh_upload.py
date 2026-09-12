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
from config import settings

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
    # Keep the tables so we don't mess up concurrent tests
    # We can delete from meshes to isolate
    db = SessionLocal()
    db.execute(Base.metadata.tables['meshes'].delete())
    db.commit()
    db.close()

def create_valid_mesh_bytes():
    mesh = trimesh.creation.box((10, 10, 10))
    f = BytesIO()
    mesh.export(f, file_type='stl')
    return f.getvalue()

def test_mesh_upload_success():
    file_bytes = create_valid_mesh_bytes()
    response = client.post(
        "/meshes",
        files={"file": ("test.stl", file_bytes, "application/octet-stream")}
    )
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data
    assert "hash" in data
    
    # Check that artifact actually saved
    # The hash should be predictable if it's the exact same bytes, but let's just use the returned one
    hash_str = data["hash"]
    expected_path = os.path.join(settings.artifact_storage_uri.replace("file://", ""), "meshes", hash_str)
    assert os.path.exists(expected_path)
    
def test_mesh_upload_deduplication():
    file_bytes = create_valid_mesh_bytes()
    response1 = client.post(
        "/meshes",
        files={"file": ("test.stl", file_bytes, "application/octet-stream")}
    )
    assert response1.status_code == 200
    id1 = response1.json()["id"]
    
    response2 = client.post(
        "/meshes",
        files={"file": ("test.stl", file_bytes, "application/octet-stream")}
    )
    assert response2.status_code == 200
    id2 = response2.json()["id"]
    
    assert id1 == id2
    
def test_mesh_upload_invalid_envelope():
    # Make a tiny file that is definitely not a valid binary STL
    invalid_bytes = b"This is not a valid STL binary file because it is too small."
    response = client.post(
        "/meshes",
        files={"file": ("invalid.stl", invalid_bytes, "application/octet-stream")}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "diagnostics" in data
    assert len(data["diagnostics"]) > 0
    assert data["diagnostics"][0]["code"] == "FILE_TOO_SMALL"
