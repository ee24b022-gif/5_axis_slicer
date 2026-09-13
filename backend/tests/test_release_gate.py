import pytest
import uuid
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from main import app
from database import engine, Base, SessionLocal
from models import Job, User, MachineProfile, Mesh, Export
from enums import JobStatus, ExportStatus, GCodeDialect, MeshFormat, JobMode, UserRole
from preprint_checklist import PreprintChecklist, ReleaseGateResult
from release_gate import ReleaseGateService
from dependencies import get_current_actor, Actor

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


@pytest.fixture(autouse=True)
def override_auth():
    admin_user = User(
        id=uuid.uuid4(),
        username="release_admin_" + uuid.uuid4().hex[:8],
        email="release_" + uuid.uuid4().hex[:8] + "@example.com",
        hashed_password="pw",
        role=UserRole.ADMIN,
    )
    actor = Actor(
        actor_type="USER",
        user_id=admin_user.id,
        key_id=None,
        scopes=["*"],
        user=admin_user,
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    yield
    app.dependency_overrides.clear()


def _make_complete_job_with_export():
    """Helper to create a COMPLETE job with a READY export in the test DB."""
    db = SessionLocal()
    user = User(
        username=f"rel_{uuid.uuid4().hex[:8]}",
        email=f"rel_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="pw",
    )
    db.add(user)
    db.commit()

    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"},
    }

    profile = MachineProfile(
        name=f"RelTest_{uuid.uuid4().hex[:8]}",
        revision=1,
        dialect="MARLIN",
        contract=valid_contract,
        limits={"ranges": {"X": [0, 300]}},
        is_active=True,
        author_id=user.id,
    )
    mesh = Mesh(
        uploader_id=user.id,
        storage_uri="file:///tmp/rel_test.stl",
        format=MeshFormat.STL_BINARY,
        size_bytes=100,
        content_hash=f"h_{uuid.uuid4().hex[:8]}",
        triangle_count=10,
        bound_min_x=0, bound_min_y=0, bound_min_z=0,
        bound_max_x=50, bound_max_y=50, bound_max_z=50,
    )
    db.add_all([profile, mesh])
    db.commit()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    job = Job(
        creator_id=user.id,
        mesh_id=mesh.id,
        machine_profile_id=profile.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash="relhash",
        status=JobStatus.COMPLETE,
        progress=1.0,
        started_at=now,
        completed_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    export = Export(
        job_id=job.id,
        creator_id=user.id,
        dialect="MARLIN",
        status=ExportStatus.READY,
        storage_uri="file:///tmp/rel_test.gcode",
        export_metadata={
            "status": ExportStatus.READY.value,
            "safety_label": "PROTOTYPE - USE WITH CAUTION",
        },
    )
    db.add(export)
    db.commit()
    db.refresh(export)

    job_id = str(job.id)
    db.close()
    return job_id


# ─── Unit tests for PreprintChecklist ────────────────────────────────────────


def test_empty_checklist_is_incomplete():
    checklist = PreprintChecklist()
    assert not checklist.is_complete
    assert len(checklist.missing_items) == 8


def test_partial_checklist_reports_missing():
    checklist = PreprintChecklist(
        homing_verified=True,
        center_position_confirmed=True,
    )
    assert not checklist.is_complete
    assert "homing_verified" not in checklist.missing_items
    assert "center_position_confirmed" not in checklist.missing_items
    assert "ab_zero_convention_checked" in checklist.missing_items
    assert len(checklist.missing_items) == 6


def test_complete_checklist():
    checklist = PreprintChecklist(
        homing_verified=True,
        center_position_confirmed=True,
        ab_zero_convention_checked=True,
        rotary_mapping_reviewed=True,
        table_clearance_checked=True,
        travel_limits_validated=True,
        firmware_behavior_acknowledged=True,
        prototype_label_acknowledged=True,
    )
    assert checklist.is_complete
    assert checklist.missing_items == []


# ─── Unit tests for ReleaseGateService ───────────────────────────────────────


def test_release_gate_blocks_incomplete_checklist():
    job = MagicMock()
    job.status = JobStatus.COMPLETE
    job.machine_profile = MagicMock()
    job.machine_profile.dialect = GCodeDialect.MARLIN
    job.diagnostics = []

    export = MagicMock()
    export.status = ExportStatus.READY
    export.dialect = GCodeDialect.MARLIN
    export.export_metadata = {
        "status": ExportStatus.READY.value,
        "safety_label": "PROTOTYPE - USE WITH CAUTION",
    }

    checklist = PreprintChecklist()  # all False
    result = ReleaseGateService.evaluate(job, export, checklist)

    assert not result.authorized
    assert result.export_gate_passed
    assert not result.checklist_complete
    assert len(result.missing_items) == 8
    assert "Pre-print checklist incomplete" in result.release_notes


def test_release_gate_authorizes_complete():
    job = MagicMock()
    job.status = JobStatus.COMPLETE
    job.machine_profile = MagicMock()
    job.machine_profile.dialect = GCodeDialect.MARLIN
    job.diagnostics = []

    export = MagicMock()
    export.status = ExportStatus.READY
    export.dialect = GCodeDialect.MARLIN
    export.export_metadata = {
        "status": ExportStatus.READY.value,
        "safety_label": "PROTOTYPE - USE WITH CAUTION",
    }

    checklist = PreprintChecklist(
        homing_verified=True,
        center_position_confirmed=True,
        ab_zero_convention_checked=True,
        rotary_mapping_reviewed=True,
        table_clearance_checked=True,
        travel_limits_validated=True,
        firmware_behavior_acknowledged=True,
        prototype_label_acknowledged=True,
    )
    result = ReleaseGateService.evaluate(job, export, checklist)

    assert result.authorized
    assert result.export_gate_passed
    assert result.checklist_complete
    assert result.missing_items == []
    assert "AUTHORIZED" in result.release_notes
    assert result.safety_label == "PROTOTYPE - USE WITH CAUTION"


def test_release_gate_blocks_when_export_blocked():
    job = MagicMock()
    job.status = JobStatus.PARTIAL  # not COMPLETE → export gate blocks
    job.machine_profile = MagicMock()
    job.machine_profile.dialect = GCodeDialect.MARLIN
    job.diagnostics = []

    export = MagicMock()
    export.status = ExportStatus.READY
    export.dialect = GCodeDialect.MARLIN
    export.export_metadata = {}

    # Even a complete checklist shouldn't override a blocked export gate
    checklist = PreprintChecklist(
        homing_verified=True,
        center_position_confirmed=True,
        ab_zero_convention_checked=True,
        rotary_mapping_reviewed=True,
        table_clearance_checked=True,
        travel_limits_validated=True,
        firmware_behavior_acknowledged=True,
        prototype_label_acknowledged=True,
    )
    result = ReleaseGateService.evaluate(job, export, checklist)

    assert not result.authorized
    assert not result.export_gate_passed
    assert "BLOCKED" in result.release_notes


# ─── Integration test for the API endpoint ───────────────────────────────────


def test_release_gate_endpoint_incomplete():
    job_id = _make_complete_job_with_export()
    response = client.post(
        f"/jobs/{job_id}/release-gate",
        json={},  # all checklist items default to False
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authorized"] is False
    assert data["checklist_complete"] is False
    assert len(data["missing_items"]) == 8


def test_release_gate_endpoint_complete():
    job_id = _make_complete_job_with_export()
    response = client.post(
        f"/jobs/{job_id}/release-gate",
        json={
            "homing_verified": True,
            "center_position_confirmed": True,
            "ab_zero_convention_checked": True,
            "rotary_mapping_reviewed": True,
            "table_clearance_checked": True,
            "travel_limits_validated": True,
            "firmware_behavior_acknowledged": True,
            "prototype_label_acknowledged": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authorized"] is True
    assert data["checklist_complete"] is True
    assert data["export_gate_passed"] is True
    assert data["missing_items"] == []
    assert "PROTOTYPE" in data["safety_label"]
