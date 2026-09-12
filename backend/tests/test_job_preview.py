import pytest
from fastapi.testclient import TestClient
from main import app
import uuid
from database import engine, Base, SessionLocal
from models import Job, User, MachineProfile, Mesh, Layer, Chunk
from enums import JobMode, JobStatus
from datetime import datetime, timezone

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
def sample_job_with_layers():
    db = SessionLocal()
    
    user = db.query(User).filter_by(username="preview_test").first()
    if not user:
        user = User(username="preview_test", email="preview@example.com", hashed_password="pw")
        db.add(user)
        db.commit()
        db.refresh(user)
        
    profile = MachineProfile(
        name="Preview Machine",
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
        limits={"ranges": {"X": (-100, 100), "Y": (-100, 100), "Z": (0, 200), "B": (-90, 90), "C": (-360, 360)}}
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    mesh = Mesh(
        uploader_id=user.id,
        content_hash="mock_hash_prev",
        storage_uri="file:///mock/path_prev",
        format="stl_binary",
        size_bytes=100,
        triangle_count=12,
        bound_min_x=0, bound_min_y=0, bound_min_z=0,
        bound_max_x=10, bound_max_y=10, bound_max_z=10
    )
    db.add(mesh)
    db.commit()
    db.refresh(mesh)
    
    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="0.1.0",
        input_hash="mock_hash_prev",
        status=JobStatus.COMPLETE,
        progress=1.0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Insert Chunk
    chunk = Chunk(
        job_id=job.id,
        chunk_idx=0,
        source_plane={"n": [0,0,1], "d": 0},
        transform_matrix=[1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
        layer_idx_min=0,
        layer_idx_max=2,
        min_z=0.0,
        max_z=10.0,
        storage_key="mock_chunk_key"
    )
    db.add(chunk)
    db.commit()
    
    # Insert Layers
    layers = []
    for i in range(4):
        layers.append(Layer(
            job_id=job.id,
            layer_idx=i,
            z_height=i * 0.2,
            thickness=0.2,
            is_planar=True,
            is_support=(i == 1), # Layer 1 is support
            preview_uri=f"file:///mock/preview_{i}.json.gz"
        ))
    
    db.add_all(layers)
    db.commit()
    
    j_id = str(job.id)
    db.close()
    return j_id

def test_get_preview_all_layers(sample_job_with_layers):
    response = client.get(f"/jobs/{sample_job_with_layers}/preview")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == sample_job_with_layers
    assert len(data["layers"]) == 4
    assert data["layers"][0]["preview_uri"] == "file:///mock/preview_0.json.gz"

def test_get_preview_filter_chunk(sample_job_with_layers):
    response = client.get(f"/jobs/{sample_job_with_layers}/preview?chunk_idx=0")
    assert response.status_code == 200
    data = response.json()
    # Chunk 0 covers layers 0 to 2
    assert len(data["layers"]) == 3
    assert data["layers"][-1]["layer_idx"] == 2

def test_get_preview_filter_layer_range(sample_job_with_layers):
    response = client.get(f"/jobs/{sample_job_with_layers}/preview?layer_idx_min=2&layer_idx_max=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["layers"]) == 2
    assert data["layers"][0]["layer_idx"] == 2
    assert data["layers"][1]["layer_idx"] == 3

def test_get_preview_exclude_supports(sample_job_with_layers):
    response = client.get(f"/jobs/{sample_job_with_layers}/preview?include_supports=false")
    assert response.status_code == 200
    data = response.json()
    assert len(data["layers"]) == 3
    # Layer 1 was support
    for layer in data["layers"]:
        assert not layer["is_support"]
        assert layer["layer_idx"] != 1

def test_get_preview_not_found():
    response = client.get(f"/jobs/{str(uuid.uuid4())}/preview")
    assert response.status_code == 404

import pytest
from dependencies import get_current_actor, Actor
from main import app
from enums import UserRole
import uuid

@pytest.fixture(autouse=True)
def override_auth_admin():
    from models import User
    admin_user = User(id=uuid.uuid4(), username="test_admin_" + str(uuid.uuid4())[:8], email="admin_" + str(uuid.uuid4())[:8] + "@example.com", hashed_password="pw", role=UserRole.ADMIN)
    actor = Actor(
        actor_type="USER",
        user_id=admin_user.id,
        key_id=None,
        scopes=["*"],
        user=admin_user
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    yield
    app.dependency_overrides.clear()
