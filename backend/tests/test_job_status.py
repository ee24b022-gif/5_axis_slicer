import pytest
from fastapi.testclient import TestClient
from main import app
import uuid
from database import engine, Base, SessionLocal
from models import Job, User, MachineProfile, Mesh
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
def sample_job_id():
    db = SessionLocal()
    
    user = db.query(User).filter_by(username="status_test").first()
    if not user:
        user = User(username="status_test", email="status@example.com", hashed_password="pw")
        db.add(user)
        db.commit()
        db.refresh(user)
        
    profile = MachineProfile(
        name="Status Machine",
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
        content_hash="mock_hash",
        storage_uri="file:///mock/path",
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
        settings={"layer_height": 0.2},
        engine_revision="0.1.0",
        input_hash="mock_hash",
        status=JobStatus.RUNNING,
        progress=0.5,
        checkpoint_data={"last_layer": 5},
        started_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    j_id = str(job.id)
    db.close()
    return j_id


def test_get_job_status_success(sample_job_id):
    response = client.get(f"/jobs/{sample_job_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == sample_job_id
    assert data["status"] == "running"
    assert data["progress"] == 0.5
    assert data["checkpoint_data"] == {"last_layer": 5}
    assert data["started_at"] is not None
    assert data["completed_at"] is None
    assert "created_at" in data
    assert "updated_at" in data

def test_get_job_status_not_found():
    response = client.get(f"/jobs/{str(uuid.uuid4())}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"
