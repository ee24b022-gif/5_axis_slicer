import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, Mesh, Job, Export, MachineProfile
from enums import JobMode, JobStatus, ExportStatus
from config import settings
from celery_app import celery_app, trigger_artifact_cleanup, cleanup_mesh_artifact, cleanup_export_artifact
from storage import get_storage_adapter
import uuid

celery_app.conf.task_always_eager = True

@pytest.fixture
def db():
    db = SessionLocal()
    yield db
    db.close()

@pytest.fixture
def storage():
    return get_storage_adapter()

def test_trigger_artifact_cleanup(db, storage):
    # Setup test data
    user = User(username="cleanup_test_user_" + str(uuid.uuid4()), email="cleanup@example.com" + str(uuid.uuid4()), hashed_password="pw")
    db.add(user)
    db.commit()
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.artifact_retention_days)
    
    # 1. Mesh that is old, no active jobs -> should be cleaned up
    mesh_old_id = uuid.uuid4()
    mesh_old_uri = storage.save_artifact(f"meshes", b"old_mesh", f"old_hash_{mesh_old_id}")
    mesh_old = Mesh(
        id=mesh_old_id, uploader_id=user.id, content_hash=f"old_hash_{mesh_old_id}", storage_uri=mesh_old_uri,
        size_bytes=10, triangle_count=1, bound_min_x=0, bound_min_y=0, bound_min_z=0, bound_max_x=1, bound_max_y=1, bound_max_z=1
    )
    mesh_old.created_at = cutoff - timedelta(days=1)
    
    # 2. Mesh that is old, but HAS a recent job -> should NOT be cleaned up
    mesh_retained_id = uuid.uuid4()
    mesh_retained_uri = storage.save_artifact(f"meshes", b"retained_mesh", f"retained_hash_{mesh_retained_id}")
    mesh_retained = Mesh(
        id=mesh_retained_id, uploader_id=user.id, content_hash=f"retained_hash_{mesh_retained_id}", storage_uri=mesh_retained_uri,
        size_bytes=10, triangle_count=1, bound_min_x=0, bound_min_y=0, bound_min_z=0, bound_max_x=1, bound_max_y=1, bound_max_z=1
    )
    mesh_retained.created_at = cutoff - timedelta(days=2)
    
    # 3. Export that is old -> should be cleaned up
    export_old_id = uuid.uuid4()
    export_old_uri = storage.save_artifact(f"exports", b"old_export", f"old_export_hash_{export_old_id}")
    
    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "AC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0},
        "command_templates": {"linear_move": "G1"}
    }
    valid_limits = {
        "ranges": {"X": (0.0, 100.0), "Y": (0.0, 100.0), "Z": (0.0, 100.0)}
    }
    
    profile = MachineProfile(name="cleanup_profile_" + str(uuid.uuid4()), revision=1, dialect="marlin", contract=valid_contract, limits=valid_limits, author_id=user.id)
    db.add(profile)
    db.commit()
    
    job = Job(
        creator_id=user.id, mesh_id=mesh_retained.id, machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS, settings={}, engine_revision="1", input_hash="hash"
    )
    job.created_at = cutoff + timedelta(days=1) # Recent
    
    db.add(mesh_old)
    db.add(mesh_retained)
    db.add(job)
    db.commit()
    
    export_old = Export(
        id=export_old_id, job_id=job.id, creator_id=user.id, dialect="marlin",
        status=ExportStatus.READY, storage_uri=export_old_uri
    )
    export_old.created_at = cutoff - timedelta(days=1)
    db.add(export_old)
    db.commit()
    
    # Run cleanup
    trigger_artifact_cleanup()
    
    db.refresh(mesh_old)
    db.refresh(mesh_retained)
    db.refresh(export_old)
    
    # Mesh 1 should be cleaned up
    assert mesh_old.cleaned_up_at is not None
    assert not storage.exists(mesh_old_uri)
    
    # Mesh 2 should be retained because of the recent job
    assert mesh_retained.cleaned_up_at is None
    assert storage.exists(mesh_retained_uri)
    
    # Export 1 should be cleaned up
    assert export_old.cleaned_up_at is not None
    assert not storage.exists(export_old_uri)
