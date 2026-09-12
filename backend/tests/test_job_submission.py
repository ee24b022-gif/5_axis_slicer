import pytest
from fastapi.testclient import TestClient
from main import app
import trimesh
from io import BytesIO
import uuid
import os
import time
from database import engine, Base, SessionLocal
from models import MachineProfile, User
from enums import JobMode
from dependencies import get_current_actor, Actor

@pytest.fixture(scope="module")
def default_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="test_uploader").first()
    if not user:
        user = User(username="test_uploader", email="test@example.com", hashed_password="pw", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@pytest.fixture(scope="module", autouse=True)
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
    # Teardown
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

def create_valid_mesh_bytes():
    mesh = trimesh.creation.box((10, 10, 10))
    f = BytesIO()
    mesh.export(f, file_type='stl')
    return f.getvalue()

@pytest.fixture(scope="module")
def sample_mesh_id():
    file_bytes = create_valid_mesh_bytes()
    resp = client.post(
        "/meshes",
        files={"file": ("test.stl", file_bytes, "application/octet-stream")}
    )
    assert resp.status_code == 200
    return resp.json()["id"]

@pytest.fixture(scope="module")
def sample_machine_profile_id():
    db = SessionLocal()
    user = db.query(User).filter_by(username="test_uploader").first()
    if not user:
        user = User(username="test_uploader", email="test@example.com", hashed_password="pw")
        db.add(user)
        db.commit()
        db.refresh(user)
        
    profile = MachineProfile(
        name="Test Machine",
        revision=1,
        dialect="gcode",
        author_id=user.id,
        contract={
            "calibration_revision": 1,
            "kinematic_convention": "AC_TABLE",
            "units": "mm",
            "axis_names": ["X", "Y", "Z", "B", "C"],
            "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": 1, "C": 1},
            "zero_positions": {"X": 0, "Y": 0, "Z": 0, "B": 0, "C": 0},
            "command_templates": {"linear_move": "G1"}
        },
        limits={
            "ranges": {
                "X": (-100, 100),
                "Y": (-100, 100),
                "Z": (0, 200),
                "B": (-90, 90),
                "C": (-360, 360)
            }
        }
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    p_id = str(profile.id)
    db.close()
    return p_id

def test_submit_job_success(sample_mesh_id, sample_machine_profile_id):
    payload = {
        "mesh_id": sample_mesh_id,
        "machine_profile_id": sample_machine_profile_id,
        "mode": "three_axis",
        "settings": {"layer_height": 0.2}
    }
    
    with TestClient(app) as local_client:
        response = local_client.post("/jobs", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"
    assert data["mode"] == "three_axis"
    assert data["progress"] == 0.0

def test_submit_job_invalid_mesh(sample_machine_profile_id):
    payload = {
        "mesh_id": str(uuid.uuid4()),
        "machine_profile_id": sample_machine_profile_id,
        "mode": "three_axis",
        "settings": {}
    }
    with TestClient(app) as local_client:
        response = local_client.post("/jobs", json=payload)
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Mesh not found"

def test_submit_job_invalid_profile(sample_mesh_id):
    payload = {
        "mesh_id": sample_mesh_id,
        "machine_profile_id": str(uuid.uuid4()),
        "mode": "three_axis",
        "settings": {}
    }
    with TestClient(app) as local_client:
        response = local_client.post("/jobs", json=payload)
    
    assert response.status_code == 404
    assert response.json()["detail"] == "Machine profile not found"
