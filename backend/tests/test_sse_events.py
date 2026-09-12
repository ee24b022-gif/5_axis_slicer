import pytest
from fastapi.testclient import TestClient
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import json
from datetime import datetime, timezone

from main import app
from database import engine, Base, SessionLocal
from models import Job, User
from enums import JobStatus

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
def mock_job():
    db = SessionLocal()
    user = User(username=f"test_{uuid.uuid4().hex[:8]}", email="sse@example.com", hashed_password="pw")
    db.add(user)
    db.commit()
    
    from models import MachineProfile, Mesh
    from enums import MeshFormat, JobMode
    
    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"}
    }
    
    profile = MachineProfile(name=f"Test_{uuid.uuid4().hex[:8]}", revision=1, dialect="MARLIN", contract=valid_contract, limits={"ranges": {"X": [0, 300]}}, is_active=True, author_id=user.id)
    mesh = Mesh(uploader_id=user.id, storage_uri="file:///tmp/x.stl", format=MeshFormat.STL_BINARY, size_bytes=1, content_hash=f"h_{uuid.uuid4().hex[:8]}", triangle_count=1, bound_min_x=0, bound_min_y=0, bound_min_z=0, bound_max_x=1, bound_max_y=1, bound_max_z=1)
    db.add_all([profile, mesh])
    db.commit()
    
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1.0", input_hash="hash", status=JobStatus.PENDING, progress=0.5)
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = str(job.id)
    db.close()
    return job_id

def test_sse_events_terminal_state():
    db = SessionLocal()
    user = User(username=f"test_{uuid.uuid4().hex[:8]}", email="term@example.com", hashed_password="pw")
    db.add(user)
    db.commit()
    
    from models import MachineProfile, Mesh
    from enums import MeshFormat, JobMode
    
    valid_contract = {
        "calibration_revision": 1,
        "kinematic_convention": "BC_TABLE",
        "units": "mm",
        "axis_names": ["X", "Y", "Z", "B", "C"],
        "axis_directions": {"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        "command_templates": {"linear_move": "G1"}
    }
    
    profile = MachineProfile(name=f"Test_{uuid.uuid4().hex[:8]}", revision=1, dialect="MARLIN", contract=valid_contract, limits={"ranges": {"X": [0, 300]}}, is_active=True, author_id=user.id)
    mesh = Mesh(uploader_id=user.id, storage_uri="file:///tmp/x.stl", format=MeshFormat.STL_BINARY, size_bytes=1, content_hash=f"h_{uuid.uuid4().hex[:8]}", triangle_count=1, bound_min_x=0, bound_min_y=0, bound_min_z=0, bound_max_x=1, bound_max_y=1, bound_max_z=1)
    db.add_all([profile, mesh])
    db.commit()
    
    job = Job(creator_id=user.id, mesh_id=mesh.id, machine_profile_id=profile.id, mode=JobMode.THREE_AXIS, settings={}, engine_revision="1.0", input_hash="hash", status=JobStatus.COMPLETE, progress=1.0, completed_at=datetime.now(timezone.utc))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = str(job.id)
    db.close()
    
    with client.stream("GET", f"/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        content = response.read().decode("utf-8")
        assert "data:" in content
        assert "artifact_persistence" in content
        assert "1.0" in content

@patch("routers.jobs.redis_async.from_url")
def test_sse_events_active_state(mock_from_url, mock_job):
    job_id = mock_job
    
    # Mock Redis client and pubsub
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_from_url.return_value = mock_client
    mock_client.pubsub.return_value = mock_pubsub
    
    async def mock_listen():
        yield {"type": "message", "data": '{"stage":"sectioning","progress":0.5}'}
        yield {"type": "message", "data": '{"stage":"sectioning","progress":0.6}'}
        # Break the loop to prevent the test from hanging
        return

    mock_pubsub.listen = mock_listen
    
    with client.stream("GET", f"/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        content = response.read().decode("utf-8")
        
        # Two data payloads should have been yielded
        assert '"progress":0.5' in content
        assert '"progress":0.6' in content
        
    # Ensure cleanup happened
    mock_pubsub.unsubscribe.assert_called_once()
    mock_client.aclose.assert_called_once()
