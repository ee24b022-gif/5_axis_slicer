import pytest
import os
import uuid
import tempfile
from fastapi.testclient import TestClient
from main import app
from database import engine, Base, SessionLocal
from models import Job, User, MachineProfile, Mesh, Export
from enums import JobMode, JobStatus, ExportStatus, GCodeDialect
from dependencies import get_current_actor, Actor

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_auth(default_user):
    actor = Actor(
        actor_type="USER",
        user_id=default_user.id,
        key_id=None,
        scopes=[],
        user=default_user
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    yield
    app.dependency_overrides.clear()

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
            email="test_upload@example.com",
            hashed_password="hashed_pw"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@pytest.fixture(scope="module")
def other_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="other_user").first()
    if not user:
        user = User(
            username="other_user",
            email="other@example.com",
            hashed_password="hashed_pw"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

@pytest.fixture(scope="module")
def base_entities(default_user):
    db = SessionLocal()
    
    mesh = Mesh(
        uploader_id=default_user.id,
        storage_uri="s3://mesh",
        format="STL_BINARY",
        size_bytes=100,
        content_hash="hash",
        triangle_count=100,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    db.add(mesh)
    
    mp = MachineProfile(
        name="test_machine",
        revision=1,
        author_id=default_user.id,
        dialect="MARLIN",
        contract={"calibration_revision": 1, "kinematic_convention": "BC_TABLE", "units": "mm", "axis_names": ["X", "Y", "Z", "B", "C"], "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1}, "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0}, "command_templates": {"linear_move": "G1"}},
        limits={"ranges": {"X": (0, 300)}}
    )
    db.add(mp)
    
    db.commit()
    db.refresh(mesh)
    db.refresh(mp)
    db.close()
    
    return mesh, mp

def test_export_success(default_user, base_entities):
    db = SessionLocal()
    mesh, mp = base_entities
    from datetime import datetime, timezone
    
    # Create temp file
    fd, temp_path = tempfile.mkstemp(suffix=".gcode")
    with os.fdopen(fd, 'w') as f:
        f.write("G0 X10 Y10 Z10")
        
    job = Job(
        creator_id=default_user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash_success",
        status=JobStatus.COMPLETE,
        progress=1.0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    
    export = Export(
        job_id=job.id,
        creator_id=default_user.id,
        dialect="MARLIN",
        status=ExportStatus.READY,
        storage_uri=f"file://{temp_path}",
        export_metadata={"status": ExportStatus.READY.value, "safety_label": "PRODUCTION"}
    )
    db.add(export)
    db.commit()
    job_id = job.id
    db.close()
    
    response = client.get(f"/jobs/{job_id}/export")
    assert response.status_code == 200
    assert response.content == b"G0 X10 Y10 Z10"
    
    os.remove(temp_path)

def test_export_incomplete_job(default_user, base_entities):
    db = SessionLocal()
    mesh, mp = base_entities
    from datetime import datetime, timezone
    
    job = Job(
        creator_id=default_user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash_incomplete",
        status=JobStatus.RUNNING,
        progress=0.5,
        started_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    
    export = Export(
        job_id=job.id,
        creator_id=default_user.id,
        dialect="MARLIN",
        status=ExportStatus.READY,
        storage_uri="file:///path/to/incomplete.gcode",
        export_metadata={"status": ExportStatus.READY.value, "safety_label": "PRODUCTION"}
    )
    db.add(export)
    db.commit()
    job_id = job.id
    db.close()
    
    response = client.get(f"/jobs/{job_id}/export")
    assert response.status_code == 400
    assert "Job is not complete" in response.json()["detail"]

def test_export_unauthorized(other_user, base_entities):
    db = SessionLocal()
    mesh, mp = base_entities
    from datetime import datetime, timezone
    
    # Job owned by other_user, but client uses default_user (test_uploader)
    job = Job(
        creator_id=other_user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash_unauth",
        status=JobStatus.COMPLETE,
        progress=1.0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()
    
    response = client.get(f"/jobs/{job_id}/export")
    assert response.status_code == 403

def test_export_missing_storage(default_user, base_entities):
    db = SessionLocal()
    mesh, mp = base_entities
    from datetime import datetime, timezone
    
    job = Job(
        creator_id=default_user.id,
        mesh_id=mesh.id,
        machine_profile_id=mp.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="hash_missing",
        status=JobStatus.COMPLETE,
        progress=1.0,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc)
    )
    db.add(job)
    db.commit()
    
    export = Export(
        job_id=job.id,
        creator_id=default_user.id,
        dialect="MARLIN",
        status=ExportStatus.READY,
        storage_uri="file:///path/to/nowhere.gcode",
        export_metadata={"status": ExportStatus.READY.value, "safety_label": "PRODUCTION"}
    )
    db.add(export)
    db.commit()
    job_id = job.id
    db.close()
    
    response = client.get(f"/jobs/{job_id}/export")
    assert response.status_code == 404
    assert "not found in storage" in response.json()["detail"]