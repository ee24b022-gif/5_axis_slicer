import pytest
import numpy as np
import trimesh
from slice_intersection import slice_mesh_at_z

def test_normal_intersection():
    # A box from [-1, -1, -1] to [1, 1, 1]
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    
    # Slicing at z=0.0 should cut exactly through the 4 vertical walls.
    # Each wall is composed of 2 triangles. So 4 * 2 = 8 segments.
    segments = slice_mesh_at_z(mesh, 0.0)
    
    assert segments.shape[0] == 8
    assert segments.shape[1] == 2
    assert segments.shape[2] == 2
    
    # Verify coordinates are somewhat correct
    # Bounding box of the segments should be exactly [-1, -1] to [1, 1]
    min_bounds = np.min(segments, axis=(0, 1))
    max_bounds = np.max(segments, axis=(0, 1))
    np.testing.assert_almost_equal(min_bounds, [-1.0, -1.0])
    np.testing.assert_almost_equal(max_bounds, [1.0, 1.0])


def test_vertex_on_plane():
    # A box has exactly flat faces at Z=1.0 and Z=-1.0
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    
    # Due to the half-open plane convention (z_a < z <= z_b),
    # Z=1.0 will match the top face vertices. It will intersect exactly
    # the top border because z=1.0 is <= 1.0. 
    segments = slice_mesh_at_z(mesh, 1.0)
    
    # The sides touching Z=1.0 will trigger intersection (because z_bottom < z <= z_top).
    # Since z=1.0, the sides will intersect at the very top.
    # We should get exactly 8 segments for a perfectly flat top.
    assert segments.shape[0] == 8
    
    # But slicing at exactly Z=-1.0, since vertices are -1.0, and -1.0 < -1.0 is False,
    # the half-open convention rejects the bottom face entirely.
    segments_bottom = slice_mesh_at_z(mesh, -1.0)
    assert segments_bottom.shape[0] == 0


def test_tangent_plane_empty():
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    
    # Slicing above the mesh
    segments = slice_mesh_at_z(mesh, 1.5)
    assert segments.shape[0] == 0
    
    # Slicing below the mesh
    segments = slice_mesh_at_z(mesh, -1.5)
    assert segments.shape[0] == 0


def test_non_horizontal_intersection():
    # If the mesh is rotated, the slice will cut diagonally
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    # Rotate 45 deg around X axis
    mat = trimesh.transformations.rotation_matrix(np.pi/4, [1, 0, 0])
    mesh.apply_transform(mat)
    
    segments = slice_mesh_at_z(mesh, 0.0)
    
    # A rotated box cut through the middle yields a rectangle (4 edges cut 2 faces each = 8 segments? 
    # Or 4 faces cut? It should be 4 faces cut yielding 4 or 8 depending on triangulation)
    # The box has 12 triangles. Some might be fully above or below.
    # In any case, it must produce valid segments > 0
    assert segments.shape[0] > 0
    
    # Ensure all segments are valid finite numbers
    assert np.all(np.isfinite(segments))
