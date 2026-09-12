import os
import pytest
from validation_service import ValidationService
from enums import DiagnosticStatus, JobStage
from enums import AngleUnit, RotationConvention
import numpy as np
import struct
import tempfile

def create_valid_binary_stl():
    """Creates a temporary valid binary STL file for testing."""
    fd, path = tempfile.mkstemp(suffix=".stl")
    with os.fdopen(fd, 'wb') as f:
        # Header
        f.write(b'\x00' * 80)
        # 1 triangle
        f.write(struct.pack("<I", 1))
        # Normal
        f.write(struct.pack("<3f", 0.0, 0.0, 1.0))
        # Vertices
        f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
        f.write(struct.pack("<3f", 10.0, 0.0, 0.0))
        f.write(struct.pack("<3f", 0.0, 10.0, 0.0))
        # Attribute byte count
        f.write(struct.pack("<H", 0))
    return path

def test_validate_mesh_file_success():
    path = create_valid_binary_stl()
    try:
        res, mesh = ValidationService.validate_mesh_file(path)
        # 1 triangle mesh is open, so it warns but does not fail!
        assert res.aggregate_status == DiagnosticStatus.WARNING
        assert not res.is_blocking
        assert mesh is not None
        assert len(mesh.faces) == 1
    finally:
        os.remove(path)

def test_validate_mesh_file_envelope_failure():
    # Empty file
    fd, path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)
    try:
        res, mesh = ValidationService.validate_mesh_file(path)
        assert res.aggregate_status == DiagnosticStatus.FAIL
        assert res.is_blocking
        assert mesh is None
        assert len(res.diagnostics) == 1
        assert res.diagnostics[0].code == "FILE_TOO_SMALL"
        assert res.diagnostics[0].stage == JobStage.MESH_VALIDATION
    finally:
        os.remove(path)

def test_validate_slice_plane_success():
    valid_plane = {
        "plane_origin": (0.0, 0.0, 10.0),
        "unit_normal": (0.0, 0.0, 1.0),
        "angle_pair": (0.0, 0.0),
        "angle_units": AngleUnit.DEGREES,
        "rotation_convention": RotationConvention.BC_TABLE,
        "local_x": (1.0, 0.0, 0.0),
        "local_y": (0.0, 1.0, 0.0)
    }
    res, plane = ValidationService.validate_slice_plane(valid_plane)
    assert res.aggregate_status == DiagnosticStatus.PASS
    assert plane is not None
    assert plane.unit_normal == (0.0, 0.0, 1.0)

def test_validate_slice_plane_failure():
    # Invalid unit normal (not length 1)
    invalid_plane = {
        "plane_origin": (0.0, 0.0, 10.0),
        "unit_normal": (0.0, 0.0, 2.0),
        "angle_pair": (0.0, 0.0),
        "angle_units": AngleUnit.DEGREES,
        "rotation_convention": RotationConvention.BC_TABLE,
        "local_x": (1.0, 0.0, 0.0),
        "local_y": (0.0, 1.0, 0.0)
    }
    res, plane = ValidationService.validate_slice_plane(invalid_plane)
    assert res.aggregate_status == DiagnosticStatus.FAIL
    assert plane is None
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].code == "INVALID_SLICE_PLANE"
    assert res.diagnostics[0].stage == JobStage.SECTIONING

def test_validate_slice_preflight():
    # A 20x20x20 cube sitting on the origin Z=0
    import trimesh
    import math
    from slice_plane_model import SlicePlane
    cube_mesh = trimesh.creation.box(extents=(20, 20, 20), transform=trimesh.transformations.translation_matrix([0, 0, 10]))
    
    n_y = math.sqrt(2)/2
    n_z = math.sqrt(2)/2
    
    # Plane cutting the mesh at Z=5, which fails heuristic limit (12.0)
    plane = SlicePlane(
        plane_origin=(0, 0, 5),
        unit_normal=(0, n_y, n_z),
        angle_pair=(45, 0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=(1.0, 0.0, 0.0),
        local_y=(0.0, -n_z, n_y)
    )
    
    res = ValidationService.validate_slice_preflight(cube_mesh, plane)
    assert res.aggregate_status == DiagnosticStatus.WARNING
    assert not res.is_blocking
    assert len(res.diagnostics) == 1
    assert res.diagnostics[0].code == "INSUFFICIENT_CLEARANCE"
    assert res.diagnostics[0].details["formula"] == "min(section_points.z) >= 12.0"
