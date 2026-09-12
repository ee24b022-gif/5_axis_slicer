import pytest
from fastapi.testclient import TestClient
from main import app
import uuid
from database import engine, Base, SessionLocal
from models import Job, User, MachineProfile, Mesh
from enums import JobMode, JobStatus

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
def test_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="cancel_test").first()
    if not user:
        user = User(username="cancel_test", email="cancel@example.com", hashed_password="pw")
        db.add(user)
        db.commit()
        db.refresh(user)
    u_id = user.id
    db.close()
    return u_id

@pytest.fixture(scope="module")
def test_profile(test_user):
    db = SessionLocal()
    profile = MachineProfile(
        name="Cancel Machine",
        revision=1,
        dialect="gcode",
        author_id=test_user,
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
    p_id = profile.id
    db.close()
    return p_id

@pytest.fixture(scope="module")
def test_mesh(test_user):
    db = SessionLocal()
    mesh = Mesh(
        uploader_id=test_user,
        content_hash="mock_hash_cancel",
        storage_uri="file:///mock/path_cancel",
        format="stl_binary",
        size_bytes=100,
        triangle_count=12,
        bound_min_x=0, bound_min_y=0, bound_min_z=0,
        bound_max_x=10, bound_max_y=10, bound_max_z=10
    )
    db.add(mesh)
    db.commit()
    db.refresh(mesh)
    m_id = mesh.id
    db.close()
    
    # Mock executor for tests to avoid lifespan context issues
    if not hasattr(app.state, "executor"):
        class MockExecutor:
            def cancel_job(self, j_id): pass
        app.state.executor = MockExecutor()
        
    return m_id

def test_cancel_running_job(test_user, test_profile, test_mesh):
    db = SessionLocal()
    from datetime import datetime, timezone
    job = Job(
        creator_id=test_user,
        mesh_id=test_mesh,
        machine_profile_id=test_profile,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="0.1.0",
        input_hash="mock_hash_cancel",
        status=JobStatus.RUNNING,
        progress=0.0,
        started_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    job_id = str(job.id)
    db.close()
    
    response = client.post(f"/jobs/{job_id}/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["status"].upper() == "CANCELLED"
    assert data.get("cancellation_requested_at") is not None
    
    # Repeated cancellation should be idempotent
    response_retry = client.post(f"/jobs/{job_id}/cancel")
    assert response_retry.status_code == 200

def test_cancel_completed_job_fails(test_user, test_profile, test_mesh):
    db = SessionLocal()
    from datetime import datetime, timezone
    job = Job(
        creator_id=test_user,
        mesh_id=test_mesh,
        machine_profile_id=test_profile,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="0.1.0",
        input_hash="mock_hash_cancel",
        status=JobStatus.COMPLETE,
        progress=1.0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    job_id = str(job.id)
    db.close()
    
    response = client.post(f"/jobs/{job_id}/cancel")
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_TRANSITION"

def test_cancel_nonexistent_job():
    response = client.post(f"/jobs/{str(uuid.uuid4())}/cancel")
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
