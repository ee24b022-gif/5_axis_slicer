import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import config
from main import app
from database import engine, Base, SessionLocal
from models import User, MachineProfile, Mesh
from enums import UserRole, MeshFormat

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

@pytest.fixture(scope="module")
def default_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="test_uploader").first()
    if not user:
        user = User(
            username="test_uploader",
            email="upload@example.com",
            role=UserRole.USER,
            hashed_password="pw"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@pytest.fixture(scope="module")
def setup_data(default_user):
    db = SessionLocal()
    
    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"}
    }
    
    profile = MachineProfile(
        name="Test Profile",
        revision=1,
        dialect="MARLIN",
        contract=valid_contract,
        limits={"ranges": {"X": [0, 300]}},
        is_active=True,
        author_id=default_user.id
    )
    db.add(profile)
    
    mesh = Mesh(
        uploader_id=default_user.id,
        storage_uri="file:///tmp/dummy.stl",
        format=MeshFormat.STL_BINARY,
        size_bytes=100,
        content_hash="hash",
        triangle_count=100,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    db.add(mesh)
    db.commit()
    db.refresh(profile)
    db.refresh(mesh)
    db.close()
    
    return profile, mesh

@patch("routers.jobs.settings")
@patch("celery_app.execute_job_task.delay")
def test_production_dispatch(mock_delay, mock_settings, setup_data):
    # Set settings.app_env to production
    mock_settings.app_env = "production"
    profile, mesh = setup_data
    
    payload = {
        "mesh_id": str(mesh.id),
        "machine_profile_id": str(profile.id),
        "mode": "three_axis",
        "settings": {"layer_height": 0.2}
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 201
    
    job_resp = response.json()
    assert job_resp["status"] == "pending"
    
    # Assert celery task was called
    assert mock_delay.called
    args, kwargs = mock_delay.call_args
    assert args[0] == job_resp["id"]
    assert args[1] == mesh.storage_uri
