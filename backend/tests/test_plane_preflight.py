import pytest
import math
import trimesh
from slice_plane_model import SlicePlane
from enums import AngleUnit, RotationConvention, DiagnosticSeverity, DiagnosticStatus
from plane_preflight import preflight_slice_plane

@pytest.fixture
def cube_mesh():
    # A 20x20x20 cube sitting on the origin Z=0
    return trimesh.creation.box(extents=(20, 20, 20), transform=trimesh.transformations.translation_matrix([0, 0, 10]))

# Tilted normal to bypass theta-zero guard
n_y = math.sqrt(2)/2
n_z = math.sqrt(2)/2
# Local axes orthogonal to the normal
loc_x = (1.0, 0.0, 0.0)
loc_y = (0.0, -n_z, n_y)

def test_valid_plane_intersection(cube_mesh):
    # Tilted plane cutting through the mesh (origin at Z=15)
    plane = SlicePlane(
        plane_origin=(0, 0, 23),
        unit_normal=(0, n_y, n_z),
        angle_pair=(45, 0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=loc_x,
        local_y=loc_y
    )
    
    diagnostics = preflight_slice_plane(cube_mesh, plane)
    
    assert len(diagnostics) == 0

def test_nonintersecting_plane(cube_mesh):
    # Tilted plane completely above the mesh (Z = 100)
    plane = SlicePlane(
        plane_origin=(0, 0, 100),
        unit_normal=(0, n_y, n_z),
        angle_pair=(45, 0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=loc_x,
        local_y=loc_y
    )
    
    diagnostics = preflight_slice_plane(cube_mesh, plane)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "NONINTERSECTING_PLANE"
    assert diagnostics[0].severity == DiagnosticSeverity.ERROR
    assert diagnostics[0].status == DiagnosticStatus.FAIL

def test_insufficient_clearance_heuristic(cube_mesh):
    # Tilted plane cutting the mesh at Z = 5 (heuristic fails)
    plane = SlicePlane(
        plane_origin=(0, 0, 5),
        unit_normal=(0, n_y, n_z),
        angle_pair=(45, 0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=loc_x,
        local_y=loc_y
    )
    
    diagnostics = preflight_slice_plane(cube_mesh, plane)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "INSUFFICIENT_CLEARANCE"
    assert diagnostics[0].severity == DiagnosticSeverity.WARNING
    assert diagnostics[0].status == DiagnosticStatus.WARNING
    assert diagnostics[0].details["heuristic_limit"] == 12.0
    assert diagnostics[0].details["formula"] == "min(section_points.z) >= 12.0"

def test_theta_zero_guard(cube_mesh):
    # Plane with purely vertical normal (theta=0)
    plane = SlicePlane(
        plane_origin=(0, 0, 15),
        unit_normal=(0, 0, 1),
        angle_pair=(0, 0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=(1, 0, 0),
        local_y=(0, 1, 0)
    )
    
    diagnostics = preflight_slice_plane(cube_mesh, plane)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "INVALID_PLANE_THETA_ZERO"
    assert diagnostics[0].severity == DiagnosticSeverity.ERROR
    assert diagnostics[0].status == DiagnosticStatus.FAIL
