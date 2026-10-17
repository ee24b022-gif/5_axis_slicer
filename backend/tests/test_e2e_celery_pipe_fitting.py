import os
import uuid
import pytest
from unittest.mock import patch, MagicMock
from database import SessionLocal, engine, Base
from models import Job, Mesh, MachineProfile, User, Diagnostic
from enums import JobMode, JobStatus, UserRole, MeshFormat, DiagnosticStatus
from celery_app import execute_job_task

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PIPE_STL = os.path.join(FIXTURE_DIR, "pipe_fitting.stl")

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.close()

@pytest.fixture
def pipe_job(db):
    u = User(username="celery_pipe_" + str(uuid.uuid4())[:8], email=str(uuid.uuid4())[:8] + "@t.com", role=UserRole.USER, hashed_password="pw")
    db.add(u); db.flush()
    m = Mesh(uploader_id=u.id, storage_uri="file:///tmp/pipe_fitting.stl", format=MeshFormat.STL_BINARY, size_bytes=os.path.getsize(PIPE_STL), content_hash="pipe_fitting_hash", triangle_count=0, bound_min_x=0, bound_min_y=0, bound_min_z=0, bound_max_x=0, bound_max_y=0, bound_max_z=0)
    db.add(m); db.flush()
    mp = MachineProfile(name="celery_pipe_mp", revision=1, author_id=u.id, dialect="marlin", contract={"calibration_revision": 1, "kinematic_convention": "AC_TABLE", "units": "mm", "axis_names": ["X","Y","Z","B","C"], "axis_directions": {"X":1,"Y":1,"Z":1,"B":1,"C":1}, "zero_positions": {"X":0,"Y":0,"Z":0,"B":0,"C":0}, "command_templates": {"linear_move": "G1"}}, limits={"ranges": {"X":(-200,200),"Y":(-200,200),"Z":(0,300),"B":(-90,90),"C":(-360,360)}})
    db.add(mp); db.flush()
    j = Job(creator_id=u.id, mesh_id=m.id, machine_profile_id=mp.id, mode=JobMode.THREE_AXIS, settings={"layer_height": 0.2}, engine_revision="0.1.0", input_hash="pipe_fitting_hash", status=JobStatus.PENDING)
    db.add(j); db.commit()
    db.refresh(j); db.refresh(m)
    return j, m

@patch('celery_app.get_storage_adapter')
def test_celery_eager_pipe_fitting_reports_collision(mock_get_storage, db, pipe_job):
    job, mesh = pipe_job
    assert job.status == JobStatus.PENDING
    
    with open(PIPE_STL, "rb") as f:
        stl_bytes = f.read()
    mock_storage = MagicMock()
    mock_storage.get_artifact.return_value = stl_bytes
    mock_get_storage.return_value = mock_storage

    result = execute_job_task(
        str(job.id),
        mesh.storage_uri,
        "three_axis",
        {"layer_height": 0.2},
        {}
    )

    db.expire_all()
    db.refresh(job)
    assert job.status == JobStatus.COMPLETE, f"Expected COMPLETE, got {job.status}"

    diags = db.query(Diagnostic).filter(Diagnostic.job_id == job.id).all()
    s001_pass = [d for d in diags if d.code == "S-001" and d.status == DiagnosticStatus.PASS]
    assert len(s001_pass) > 0, f"Expected passing S-001 diagnostic, got: {[(d.code, d.status, d.message) for d in diags]}"
