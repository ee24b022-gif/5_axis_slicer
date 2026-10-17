"""
End-to-end regression test: pipe_fitting.stl

pipe_fitting.stl triggers a collision detection failure in
slicer_python.slice_mesh.  This test uploads the real STL,
submits a slicing job through the HTTP API, lets the local
executor finish, and then verifies that the pipeline reports
the failure honestly.

Expected current behaviour (test should FAIL on the "happy-path"
assertions and PASS on the "failure-path" assertions):
  - job status == "failed"
  - GET /jobs/{id}/diagnostics includes a collision diagnostic
  - preview layers == 0
  - export 404
"""
import os
import uuid
import pytest
from fastapi.testclient import TestClient

from main import app
from database import engine, Base, SessionLocal
from models import User, MachineProfile
from dependencies import get_current_actor, Actor
from enums import UserRole

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ── DB + auth scaffolding (module-scoped for speed) ──────────────

@pytest.fixture(scope="module")
def default_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="e2e_pipe_fitting").first()
    if not user:
        user = User(
            username="e2e_pipe_fitting",
            email="e2e_pipe@example.com",
            hashed_password="pw",
            is_active=True,
            role=UserRole.ADMIN,
        )
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
        user=default_user,
    )
    app.dependency_overrides[get_current_actor] = lambda: actor
    yield
    app.dependency_overrides.pop(get_current_actor, None)


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
def machine_profile_id(default_user):
    db = SessionLocal()
    profile = MachineProfile(
        name="E2E Pipe Machine",
        revision=1,
        dialect="gcode",
        author_id=default_user.id,
        contract={
            "calibration_revision": 1,
            "kinematic_convention": "AC_TABLE",
            "units": "mm",
            "axis_names": ["X", "Y", "Z", "B", "C"],
            "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": 1, "C": 1},
            "zero_positions": {"X": 0, "Y": 0, "Z": 0, "B": 0, "C": 0},
            "command_templates": {"linear_move": "G1"},
        },
        limits={
            "ranges": {
                "X": (-200, 200),
                "Y": (-200, 200),
                "Z": (0, 300),
                "B": (-90, 90),
                "C": (-360, 360),
            }
        },
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    pid = str(profile.id)
    db.close()
    return pid


# ── The actual end-to-end test ───────────────────────────────────

def test_pipe_fitting_job_complete(machine_profile_id):
    """Upload pipe_fitting.stl, submit a three_axis slicing job at
    layer_height 0.2, and verify the pipeline completes successfully.

    pipe_fitting.stl previously triggered a collision detection failure
    in slicer_python.slice_mesh.  With the slicing fixes in place, the
    job should now finish with status "complete", produce preview layers,
    and expose a gcode export.
    """
    stl_path = os.path.join(FIXTURE_DIR, "pipe_fitting.stl")
    assert os.path.exists(stl_path), f"Fixture missing: {stl_path}"

    # Use `with TestClient(app)` so background tasks run to completion
    # before exit.
    with TestClient(app) as client:
        # 1. Upload the mesh
        with open(stl_path, "rb") as f:
            upload_resp = client.post(
                "/meshes",
                files={"file": ("pipe_fitting.stl", f, "application/octet-stream")},
            )
        assert upload_resp.status_code == 200, upload_resp.text
        mesh_id = upload_resp.json()["id"]

        # 2. Submit the slicing job
        job_resp = client.post(
            "/jobs",
            json={
                "mesh_id": mesh_id,
                "machine_profile_id": machine_profile_id,
                "mode": "three_axis",
                "settings": {"layer_height": 0.2},
            },
        )
        assert job_resp.status_code == 201, job_resp.text
        job_id = job_resp.json()["id"]

    # Background task has now finished (TestClient context exited).
    # Re-open a client to query results (no new background tasks).
    with TestClient(app) as client:
        # 3. Check job status
        status_resp = client.get(f"/jobs/{job_id}")
        assert status_resp.status_code == 200
        job_data = status_resp.json()
        assert job_data["status"] == "complete", (
            f"Expected job to be 'complete' but got '{job_data['status']}'"
        )

        # 4. Preview should have layers
        preview_resp = client.get(f"/jobs/{job_id}/preview")
        assert preview_resp.status_code == 200
        layers = preview_resp.json()["layers"]
        assert len(layers) > 0, "Expected preview layers > 0"

        # 5. Export should exist
        export_resp = client.get(f"/jobs/{job_id}/export")
        assert export_resp.status_code == 200, (
            f"Expected export to exist, got {export_resp.status_code}"
        )


def test_pipe_fitting_diagnostics_all_pass(machine_profile_id):
    """Upload pipe_fitting.stl, submit a job, and verify every diagnostic
    reports a passing status (none fail).

    This is the complement to test_pipe_fitting_job_complete: once the
    pipeline fixes land, the job completes and no sectioning or other
    stage diagnostics should carry a "fail" status.
    """
    stl_path = os.path.join(FIXTURE_DIR, "pipe_fitting.stl")

    with TestClient(app) as client:
        with open(stl_path, "rb") as f:
            upload_resp = client.post(
                "/meshes",
                files={"file": ("pipe_fitting.stl", f, "application/octet-stream")},
            )
        mesh_id = upload_resp.json()["id"]

        job_resp = client.post(
            "/jobs",
            json={
                "mesh_id": mesh_id,
                "machine_profile_id": machine_profile_id,
                "mode": "three_axis",
                "settings": {"layer_height": 0.2},
            },
        )
        job_id = job_resp.json()["id"]

    with TestClient(app) as client:
        # Job should be COMPLETE
        status_resp = client.get(f"/jobs/{job_id}")
        job_data = status_resp.json()
        assert job_data["status"] == "complete", (
            f"Expected job to be 'complete' but got '{job_data['status']}'"
        )

        # All diagnostics should pass (no "fail" status)
        diag_resp = client.get(f"/jobs/{job_id}/diagnostics")
        assert diag_resp.status_code == 200
        diagnostics = diag_resp.json()
        fail_diags = [d for d in diagnostics if d.get("status") == "fail"]
        assert len(fail_diags) == 0, (
            f"Expected all diagnostics to pass, got failures: {fail_diags}"
        )
