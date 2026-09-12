import pytest
from fastapi.testclient import TestClient
import uuid
from main import app
from database import engine, Base, SessionLocal
from models import User, Mesh, Job, Export, MachineProfile
from enums import JobMode, JobStatus, ExportStatus, UserRole
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

@pytest.fixture
def db():
    db = SessionLocal()
    yield db
    db.close()

@pytest.fixture
def user_a(db):
    user = db.query(User).filter_by(username="user_a").first()
    if not user:
        user = User(username="user_a", email="a@example.com", hashed_password="pw", is_active=True, role=UserRole.USER)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

@pytest.fixture
def user_b(db):
    user = db.query(User).filter_by(username="user_b").first()
    if not user:
        user = User(username="user_b", email="b@example.com", hashed_password="pw", is_active=True, role=UserRole.USER)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

@pytest.fixture
def admin_user(db):
    user = db.query(User).filter_by(username="admin_user").first()
    if not user:
        user = User(username="admin_user", email="admin@example.com", hashed_password="pw", is_active=True, role=UserRole.ADMIN)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

@pytest.fixture
def machine_profile(db, admin_user):
    profile = db.query(MachineProfile).filter_by(name="Test Profile").first()
    if not profile:
        profile = MachineProfile(
            name="Test Profile",
            revision=1,
            dialect="MARLIN",
            author_id=admin_user.id,
            contract={
                "calibration_revision": 1,
                "kinematic_convention": "AC_TABLE",
                "units": "mm",
                "axis_names": ["X", "Y", "Z", "A", "C"],
                "axis_directions": {"X": 1, "Y": 1, "Z": 1, "A": 1, "C": 1},
                "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0, "C": 0.0},
                "command_templates": {"linear": "G1 X{X} Y{Y} Z{Z}"}
            },
            limits={"ranges": {"X": [0, 200]}}
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile

@pytest.fixture
def mesh_a(db, user_a):
    mesh = Mesh(
        uploader_id=user_a.id,
        content_hash=str(uuid.uuid4()),
        storage_uri="s3://test/mesh_a.stl",
        size_bytes=100,
        triangle_count=100,
        bound_min_x=0.0, bound_min_y=0.0, bound_min_z=0.0,
        bound_max_x=10.0, bound_max_y=10.0, bound_max_z=10.0
    )
    db.add(mesh)
    db.commit()
    db.refresh(mesh)
    return mesh

@pytest.fixture
def job_a(db, user_a, mesh_a, machine_profile):
    job = Job(
        creator_id=user_a.id,
        mesh_id=mesh_a.id,
        machine_profile_id=machine_profile.id,
        mode=JobMode.THREE_AXIS,
        settings={},
        engine_revision="1.0",
        input_hash=mesh_a.content_hash,
        status=JobStatus.PENDING,
        progress=0.0
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

@pytest.fixture
def export_a(db, user_a, job_a):
    export = Export(
        job_id=job_a.id,
        creator_id=user_a.id, # Job owner owns export
        dialect="MARLIN",
        status=ExportStatus.READY,
        storage_uri="s3://test/export_a.gcode"
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return export

def auth_as(user):
    actor = Actor(
        actor_type="USER",
        user_id=user.id,
        key_id=None,
        scopes=["*"],
        user=user
    )
    app.dependency_overrides[get_current_actor] = lambda: actor

def clear_auth():
    app.dependency_overrides.clear()

def test_cross_user_job_access_denied(user_a, user_b, job_a):
    # User B tries to access User A's job
    auth_as(user_b)
    
    resp = client.get(f"/jobs/{job_a.id}")
    assert resp.status_code == 403
    
    resp = client.get(f"/jobs/{job_a.id}/diagnostics")
    assert resp.status_code == 403
    
    resp = client.get(f"/jobs/{job_a.id}/preview")
    assert resp.status_code == 403
    
    resp = client.post(f"/jobs/{job_a.id}/cancel")
    assert resp.status_code == 403
    
    clear_auth()

def test_cross_user_mesh_access_denied(user_a, user_b, mesh_a):
    auth_as(user_b)
    resp = client.get(f"/meshes/{mesh_a.id}")
    assert resp.status_code == 403
    clear_auth()

def test_owner_can_access_own_resources(user_a, job_a, mesh_a):
    auth_as(user_a)
    
    resp = client.get(f"/jobs/{job_a.id}")
    assert resp.status_code == 200
    
    resp = client.get(f"/meshes/{mesh_a.id}")
    assert resp.status_code == 200
    
    clear_auth()

def test_admin_can_access_any_resource(admin_user, job_a, mesh_a):
    auth_as(admin_user)
    
    resp = client.get(f"/jobs/{job_a.id}")
    assert resp.status_code == 200
    
    resp = client.get(f"/meshes/{mesh_a.id}")
    assert resp.status_code == 200
    
    clear_auth()

def test_export_permission_distinct(db, user_a, user_b, job_a):
    # User B creates an export for User A's job (assuming they somehow got access or did this before authorization was enforced)
    export_b = Export(
        job_id=job_a.id,
        creator_id=user_b.id,
        dialect="MARLIN",
        status=ExportStatus.READY,
        storage_uri="s3://test/export_b.gcode"
    )
    db.add(export_b)
    db.commit()
    
    # User A tries to get the export for their own job, but the latest export is owned by User B.
    auth_as(user_a)
    
    # We stub ExportGateService and storage check here or we will get a 404/400 because they don't actually exist
    # However, the ownership check happens first, so we should get 403.
    resp = client.get(f"/jobs/{job_a.id}/export")
    assert resp.status_code == 403
    
    clear_auth()

def test_machine_profiles_remain_public(machine_profile):
    clear_auth()
    # No auth
    resp = client.get("/machine-profiles")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    
    resp = client.get(f"/machine-profiles/{machine_profile.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(machine_profile.id)
