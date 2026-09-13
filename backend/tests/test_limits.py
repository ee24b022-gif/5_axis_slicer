import struct
import tempfile
import uuid
import pytest
from fastapi.testclient import TestClient
from main import app
from config import settings
from dependencies import get_db, get_current_actor, Actor
from models import User

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_auth():
    test_user = User(
        id=uuid.uuid4(),
        username="test_limit_user",
        email="test_limit@example.com",
        hashed_password="fakehash",
        role="user",
        is_active=True
    )
    
    test_actor = Actor(actor_type="USER", user_id=test_user.id, key_id=None, scopes=[], user=test_user)
    
    def override_get_current_actor():
        return test_actor
        
    app.dependency_overrides[get_current_actor] = override_get_current_actor
    yield
    app.dependency_overrides.clear()


def create_stl_bytes(triangle_count, dim_x, dim_y, dim_z):
    # Minimal binary STL with arbitrary triangle count and max dimensions
    header = b'\x00' * 80
    normal = struct.pack('<fff', 0.0, 0.0, 1.0)
    
    # We create just 2 extreme vertices to form a bounding box
    # For triangle limit, we pad with empty/degenerate triangles.
    # We can't generate huge files in tests easily without using memory,
    # so we will generate a valid STL with a small number of triangles and test dim limit first.
    # For triangle limit, we can just mock `parse_binary_stl` or generate a specific size.
    
    v1 = struct.pack('<fff', 0.0, 0.0, 0.0)
    v2 = struct.pack('<fff', dim_x, dim_y, 0.0)
    v3 = struct.pack('<fff', 0.0, 0.0, dim_z)
    attr = struct.pack('<H', 0)
    
    triangle = normal + v1 + v2 + v3 + attr
    
    data = header + struct.pack('<I', triangle_count)
    for _ in range(triangle_count):
        data += triangle
        
    return data


def test_mesh_upload_too_many_triangles(monkeypatch):
    monkeypatch.setattr(settings, "max_triangles", 2)
    
    stl_data = create_stl_bytes(3, 10.0, 10.0, 10.0)
    
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp.write(stl_data)
        tmp_name = tmp.name
        
    with open(tmp_name, "rb") as f:
        response = client.post(
            "/meshes",
            files={"file": ("test.stl", f, "application/octet-stream")}
        )
        
    assert response.status_code == 400
    diag = response.json().get("diagnostics", [])[0]
    assert diag["code"] == "TOO_MANY_TRIANGLES"


def test_mesh_upload_bounding_box_exceeded(monkeypatch):
    monkeypatch.setattr(settings, "max_bounding_box_dim_mm", 100.0)
    monkeypatch.setattr(settings, "max_triangles", 1000)
    
    # Create an STL that exceeds X dimension (150.0 > 100.0)
    stl_data = create_stl_bytes(1, 150.0, 10.0, 10.0)
    
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp.write(stl_data)
        tmp_name = tmp.name
        
    with open(tmp_name, "rb") as f:
        response = client.post(
            "/meshes",
            files={"file": ("test.stl", f, "application/octet-stream")}
        )
        
    assert response.status_code == 400
    diag = response.json().get("diagnostics", [])[0]
    assert diag["code"] == "BOUNDING_BOX_EXCEEDED"
    
def test_mesh_upload_within_limits(monkeypatch):
    monkeypatch.setattr(settings, "max_bounding_box_dim_mm", 100.0)
    monkeypatch.setattr(settings, "max_triangles", 10)
    
    # Within limits: 50.0 mm max dim, 5 triangles
    stl_data = create_stl_bytes(5, 50.0, 50.0, 50.0)
    
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp.write(stl_data)
        tmp_name = tmp.name
        
    with open(tmp_name, "rb") as f:
        response = client.post(
            "/meshes",
            files={"file": ("test.stl", f, "application/octet-stream")}
        )
        
    # Should succeed or hit another error (like auth if we didn't mock properly)
    assert response.status_code == 200
    assert "id" in response.json()

def test_celery_config_limits():
    from celery_app import celery_app
    # Verify that the celery app was configured with the expected limit keys
    assert celery_app.conf.worker_concurrency == settings.worker_concurrency
    assert celery_app.conf.task_soft_time_limit == settings.task_soft_time_limit
    assert celery_app.conf.task_time_limit == settings.task_time_limit
    assert celery_app.conf.worker_max_memory_per_child == settings.worker_max_memory_per_child
    assert celery_app.conf.worker_max_tasks_per_child == settings.worker_max_tasks_per_child
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
