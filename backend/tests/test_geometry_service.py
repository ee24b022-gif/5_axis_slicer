import pytest
import io
import trimesh
from enums import JobMode, DiagnosticStatus
from geometry_service import GeometryApplicationService

def create_valid_mesh_bytes():
    # Simple valid cube
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    f = io.BytesIO()
    mesh.export(f, file_type='stl')
    return f.getvalue()

def create_invalid_mesh_bytes():
    # Just garbage data
    return b"garbage data that is not an stl"

def test_geometry_service_blocks_invalid_mesh():
    invalid_bytes = create_invalid_mesh_bytes()
    
    result, diagnostics = GeometryApplicationService.execute(
        job_id="test_job_123",
        file_bytes=invalid_bytes,
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": 0.2, "bed_center_z": 0.0},
        machine_profile={}
    )
    
    # Execution should halt and return empty result
    assert result == {}
    
    # Should have a failing diagnostic for loading
    has_fail = any(d.status == DiagnosticStatus.FAIL for d in diagnostics)
    assert has_fail

def test_geometry_service_successful_pipeline():
    valid_bytes = create_valid_mesh_bytes()
    
    result, diagnostics = GeometryApplicationService.execute(
        job_id="test_job_123",
        file_bytes=valid_bytes,
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": 0.2, "bed_center_z": 0.0},
        machine_profile={}
    )
    
    # No fail diagnostics
    has_fail = any(d.status == DiagnosticStatus.FAIL for d in diagnostics)
    assert not has_fail
    
    # Should have toolpath_job in result
    assert "toolpath_job" in result
