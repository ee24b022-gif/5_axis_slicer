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
