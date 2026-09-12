import pytest
import numpy as np
import trimesh
from transform_utils import apply_canonical_transform

def create_unit_box():
    # A box from [-1, -1, -1] to [1, 1, 1]
    return trimesh.creation.box(extents=(2, 2, 2))

def test_scale_constraint():
    mesh = create_unit_box()
    
    with pytest.raises(ValueError) as exc:
        apply_canonical_transform(mesh, scale=0.0)
    assert "strictly positive" in str(exc.value)
    
    with pytest.raises(ValueError) as exc:
        apply_canonical_transform(mesh, scale=-1.0)
    assert "strictly positive" in str(exc.value)

def test_default_transform_anchors_and_centers():
    mesh = create_unit_box()
    # By default, a unit box is centered at (0,0,0) with Z from -1 to 1.
    # The default transform should center it at (0,0) and anchor Z at 0.
    
    updated_mesh, matrix = apply_canonical_transform(mesh)
    
    bounds = updated_mesh.bounds
    # min X, min Y, min Z
    np.testing.assert_almost_equal(bounds[0], [-1.0, -1.0, 0.0])
    # max X, max Y, max Z
    np.testing.assert_almost_equal(bounds[1], [1.0, 1.0, 2.0])
    
def test_scale_and_translate():
    mesh = create_unit_box()
    
    # Scale by 2 -> size is 4x4x4. Z should go 0 to 4.
    # Translate X by 10, Y by -5.
    # X bounds: 10 - 2 to 10 + 2 -> 8 to 12
    # Y bounds: -5 - 2 to -5 + 2 -> -7 to -3
    updated_mesh, matrix = apply_canonical_transform(
        mesh, 
        scale=2.0, 
        trans_x=10.0, 
        trans_y=-5.0
    )
    
    bounds = updated_mesh.bounds
    np.testing.assert_almost_equal(bounds[0], [8.0, -7.0, 0.0])
    np.testing.assert_almost_equal(bounds[1], [12.0, -3.0, 4.0])

def test_rotation_anchoring_order():
    # If we rotate the box 45 degrees around X, it will protrude further in Z and Y.
    # The anchoring must happen AFTER rotation to ensure the lowest point of the rotated box is exactly Z=0.
    mesh = create_unit_box()
    
    updated_mesh, matrix = apply_canonical_transform(mesh, rot_x_deg=45.0)
    
    bounds = updated_mesh.bounds
    
    # Z min must be precisely 0
    np.testing.assert_almost_equal(bounds[0][2], 0.0)
    
    # The height of a 2x2 box rotated 45 degrees is 2*sqrt(2) = 2.8284...
    expected_height = 2 * np.sqrt(2)
    np.testing.assert_almost_equal(bounds[1][2], expected_height)

def test_matrix_round_trip():
    original_mesh = create_unit_box()
    # We must deep copy to keep original vertices
    working_mesh = original_mesh.copy()
    
    updated_mesh, matrix = apply_canonical_transform(
        working_mesh, 
        scale=1.5, 
        rot_x_deg=10.0, 
        rot_y_deg=-20.0, 
        rot_z_deg=180.0, 
        trans_x=5.0, 
        trans_y=5.0
    )
    
    # Apply the inverse matrix to the updated mesh
    inv_matrix = np.linalg.inv(matrix)
    updated_mesh.apply_transform(inv_matrix)
    
    # The coordinates should exactly match the original
    np.testing.assert_almost_equal(updated_mesh.vertices, original_mesh.vertices)

from slice_plane_model import SlicePlane
from enums import AngleUnit, RotationConvention
from transform_utils import align_chunk_to_slice_plane

def test_chunk_local_frame_alignment():
    # 1. Define a 45-degree tilted plane
    # Normal is (0.707, 0, 0.707) roughly
    tilt = np.radians(45)
    plane_normal = (np.sin(tilt), 0.0, np.cos(tilt))
    plane_origin = (10.0, 0.0, 10.0)
    local_x = (np.cos(tilt), 0.0, -np.sin(tilt))
    local_y = (0.0, 1.0, 0.0)
    
    plane = SlicePlane(
        plane_origin=plane_origin,
        unit_normal=plane_normal,
        angle_pair=(45.0, 0.0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=local_x,
        local_y=local_y
    )
    
    # 2. Create a box centered at the origin, and move it to the plane.
    # The box is placed such that its bottom perfectly aligns with the plane
    box = trimesh.creation.box(extents=(10, 10, 10))
    # Move box so its bottom center is at (0,0,0)
    box.apply_translation([0, 0, 5])
    
    # We want to place this box precisely ON the plane in world space
    local_to_world = np.eye(4)
    local_to_world[0:3, 0] = plane.local_x
    local_to_world[0:3, 1] = plane.local_y
    local_to_world[0:3, 2] = plane.unit_normal
    local_to_world[0:3, 3] = plane.plane_origin
    box.apply_transform(local_to_world)
    
    # 3. Align it
    aligned_mesh, flat_matrix, min_z, max_z = align_chunk_to_slice_plane(box, plane)
    
    # 4. Assert
    # min_z should be 0 since the base of the box is on the plane
    assert abs(min_z) < 1e-4
    # max_z should be 10 (the height of the box)
    assert abs(max_z - 10.0) < 1e-4
    
    # 5. Reverse transformation test
    # Apply the returned flat_matrix to the aligned mesh
    reverse_mat = np.array(flat_matrix).reshape(4, 4)
    aligned_mesh.apply_transform(reverse_mat)
    
    # The bottom center of the reversed mesh should be exactly back at plane_origin
    # Wait, the mesh center in local was (0,0,5). In world it should be origin + 5*normal
    expected_centroid = np.array(plane_origin) + 5.0 * np.array(plane_normal)
    assert np.allclose(aligned_mesh.centroid, expected_centroid, atol=1e-4)
