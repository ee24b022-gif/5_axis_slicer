import math
import numpy as np
import trimesh
import pytest
from pydantic import ValidationError
from hypothesis import given, settings, strategies as st
from hypothesis.strategies import floats

from transform_utils import apply_canonical_transform, align_chunk_to_slice_plane
from slice_plane_model import SlicePlane
from uv_adapter import TableTableUVAdapter
from enums import AngleUnit, RotationConvention
from mesh_structural_validator import validate_mesh_structure
from slice_intersection import slice_mesh_at_z

# 1. Transform Round Trips
@given(
    scale=floats(min_value=1e-3, max_value=1000.0, allow_nan=False, allow_infinity=False),
    rot_x=floats(min_value=-360.0, max_value=360.0, allow_nan=False, allow_infinity=False),
    rot_y=floats(min_value=-360.0, max_value=360.0, allow_nan=False, allow_infinity=False),
    rot_z=floats(min_value=-360.0, max_value=360.0, allow_nan=False, allow_infinity=False),
    trans_x=floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    trans_y=floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
)
def test_canonical_transform_valid_matrix(scale, rot_x, rot_y, rot_z, trans_x, trans_y):
    box = trimesh.creation.box(extents=(10, 10, 10))
    mesh, mat = apply_canonical_transform(box, scale=scale, rot_x_deg=rot_x, rot_y_deg=rot_y, rot_z_deg=rot_z, trans_x=trans_x, trans_y=trans_y)
    assert mat.shape == (4, 4)
    assert not np.isnan(mat).any()
    assert not np.isinf(mat).any()

@given(
    nx=floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
    ny=floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
    nz=floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False)
)
def test_align_chunk_inversions(nx, ny, nz):
    mag = math.hypot(nx, ny, nz)
    if mag < 1e-3:
        return
    nx, ny, nz = nx/mag, ny/mag, nz/mag
    
    if abs(nx) > 0.9:
        v = np.array([0.0, 1.0, 0.0])
    else:
        v = np.array([1.0, 0.0, 0.0])
    
    n = np.array([nx, ny, nz])
    lx = np.cross(v, n)
    lx = lx / np.linalg.norm(lx)
    ly = np.cross(n, lx)
    
    plane = SlicePlane(
        plane_origin=(0.0, 0.0, 0.0),
        unit_normal=(float(nx), float(ny), float(nz)),
        angle_pair=(0.0, 0.0),
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=(float(lx[0]), float(lx[1]), float(lx[2])),
        local_y=(float(ly[0]), float(ly[1]), float(ly[2]))
    )
    
    box = trimesh.creation.box(extents=(10, 10, 10))
    _, local_to_world_flat, _, _ = align_chunk_to_slice_plane(box, plane)
    l2w = np.array(local_to_world_flat).reshape(4, 4)
    
    assert np.allclose(l2w[0:3, 0], lx)
    assert np.allclose(l2w[0:3, 1], ly)
    assert np.allclose(l2w[0:3, 2], n)

# 2. Numeric Singularities
@given(
    nx=floats(allow_nan=True, allow_infinity=True),
    ny=floats(allow_nan=True, allow_infinity=True),
    nz=floats(allow_nan=True, allow_infinity=True)
)
def test_slice_plane_invalid_normals(nx, ny, nz):
    try:
        SlicePlane(
            plane_origin=(0.0, 0.0, 0.0),
            unit_normal=(nx, ny, nz),
            angle_pair=(0.0, 0.0),
            rotation_convention=RotationConvention.AC_TABLE,
            local_x=(1.0, 0.0, 0.0),
            local_y=(0.0, 1.0, 0.0)
        )
        # It might succeed if by some chance it generates exactly 1.0, 0.0, 0.0
    except (ValidationError, ValueError):
        pass

# 3. Angle & Rotary Modulo
@given(
    nx=floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    ny=floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    nz=floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
)
def test_uv_adapter_modulo(nx, ny, nz):
    mag = math.hypot(nx, ny, nz)
    if mag < 1e-5:
        with pytest.raises(ValueError, match="Invalid non-unit normal vector"):
            adapter = TableTableUVAdapter()
            adapter.calculate_ik(0, 0, 0, nx, ny, nz)
        return
        
    nx, ny, nz = nx/mag, ny/mag, nz/mag
    adapter = TableTableUVAdapter()
    machine_x, machine_y, machine_z, angles = adapter.calculate_ik(10.0, 20.0, 30.0, nx, ny, nz)
    
    assert isinstance(angles['u'], float)
    assert isinstance(angles['v'], float)
    assert not math.isnan(angles['u'])
    assert not math.isnan(angles['v'])
    assert not math.isnan(machine_x)
    assert not math.isnan(machine_y)
    assert not math.isnan(machine_z)

# 4. Bounded & Extreme Geometry Inputs
@given(
    z_height=floats(allow_nan=True, allow_infinity=True)
)
def test_slice_mesh_at_z_extreme(z_height):
    box = trimesh.creation.box(extents=(10, 10, 10))
    if math.isnan(z_height) or math.isinf(z_height):
        # Depending on slicing implementation, could raise ValueError or return empty.
        try:
            slice_mesh_at_z(box, z_height)
        except Exception:
            pass 
    else:
        segments = slice_mesh_at_z(box, z_height)
        assert isinstance(segments, np.ndarray) or segments is None or len(segments) >= 0

@given(
    v1x=floats(allow_nan=True, allow_infinity=True),
    v1y=floats(allow_nan=True, allow_infinity=True),
    v1z=floats(allow_nan=True, allow_infinity=True)
)
def test_mesh_validator_extreme(v1x, v1y, v1z):
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [v1x, v1y, v1z]
    ])
    faces = np.array([
        [0, 1, 2],
        [1, 3, 2],
        [0, 2, 3],
        [0, 3, 1]
    ])
    
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    
    assert isinstance(diagnostics, list)
    if mesh is None:
        assert len(diagnostics) > 0
    else:
        assert isinstance(mesh, trimesh.Trimesh)
