import pytest
from fastapi.testclient import TestClient
from main import app
import uuid
import time
from database import engine, Base, SessionLocal
from models import Job, User, MachineProfile, Mesh, Diagnostic
from enums import JobMode, JobStatus, JobStage, DiagnosticSeverity, DiagnosticStatus
from datetime import datetime, timezone, timedelta

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
def sample_job_with_diagnostics():
    db = SessionLocal()
    
    user = db.query(User).filter_by(username="diag_test").first()
    if not user:
        user = User(username="diag_test", email="diag@example.com", hashed_password="pw")
        db.add(user)
        db.commit()
        db.refresh(user)
        
    profile = MachineProfile(
        name="Diag Machine",
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
        content_hash="mock_hash_2",
        storage_uri="file:///mock/path2",
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
        input_hash="mock_hash_2",
        status=JobStatus.RUNNING,
        progress=0.0
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Insert diagnostics with simulated chronological delay
    now = datetime.now(timezone.utc)
    
    diag1 = Diagnostic(
        job_id=job.id,
        stage=JobStage.MESH_VALIDATION,
        severity=DiagnosticSeverity.INFO,
        status=DiagnosticStatus.PASS,
        code="MESH_OK",
        message="Mesh looks fine",
        created_at=now
    )
    
    diag2 = Diagnostic(
        job_id=job.id,
        stage=JobStage.CANONICAL_FRAME,
        severity=DiagnosticSeverity.WARNING,
        status=DiagnosticStatus.WARNING,
        code="FRAME_WARN",
        message="Frame shifted slightly",
        created_at=now + timedelta(seconds=1)
    )
    
    diag3 = Diagnostic(
        job_id=job.id,
        stage=JobStage.SECTIONING,
        severity=DiagnosticSeverity.ERROR,
        status=DiagnosticStatus.FAIL,
        code="SEC_ERR",
        message="Sectioning failed on polygon intersection",
        created_at=now + timedelta(seconds=2)
    )
    
    db.add_all([diag1, diag2, diag3])
    db.commit()
    
    j_id = str(job.id)
    db.close()
    return j_id


def test_get_job_diagnostics_all(sample_job_with_diagnostics):
    response = client.get(f"/jobs/{sample_job_with_diagnostics}/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    
    # Assert chronological order
    assert data[0]["code"] == "MESH_OK"
    assert data[1]["code"] == "FRAME_WARN"
    assert data[2]["code"] == "SEC_ERR"

def test_get_job_diagnostics_filter_severity(sample_job_with_diagnostics):
    response = client.get(f"/jobs/{sample_job_with_diagnostics}/diagnostics?severity=warning")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["code"] == "FRAME_WARN"

def test_get_job_diagnostics_filter_stage(sample_job_with_diagnostics):
    response = client.get(f"/jobs/{sample_job_with_diagnostics}/diagnostics?stage=sectioning")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["code"] == "SEC_ERR"

def test_get_job_diagnostics_filter_multiple(sample_job_with_diagnostics):
    response = client.get(f"/jobs/{sample_job_with_diagnostics}/diagnostics?stage=sectioning&severity=info")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0

def test_get_job_diagnostics_not_found():
    response = client.get(f"/jobs/{str(uuid.uuid4())}/diagnostics")
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"

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
