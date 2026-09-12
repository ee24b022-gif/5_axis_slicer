import pytest
import trimesh
import numpy as np
from auto_segment import AutoSegmenter

def test_auto_segment_disabled():
    cube = trimesh.creation.box(extents=(10, 10, 10))
    cube.apply_translation([0, 0, 5])
    
    planes = AutoSegmenter.compute_segmentation(cube, enable_auto_segment=False)
    
    assert len(planes) == 1
    assert planes[0].unit_normal == (0.0, 0.0, 1.0)
    assert planes[0].plane_origin == (0.0, 0.0, 0.0)

def test_auto_segment_no_overhangs():
    # A simple cube has no downward facing overhangs above min_z + 2.0
    cube = trimesh.creation.box(extents=(10, 10, 10))
    cube.apply_translation([0, 0, 5]) # min_z = 0, downward face is at z=0 (not > 2.0)
    
    planes = AutoSegmenter.compute_segmentation(cube, enable_auto_segment=True)
    assert len(planes) == 1
    assert planes[0].unit_normal == (0.0, 0.0, 1.0)

def test_auto_segment_with_overhangs():
    # Create an L-shaped bracket (an overhang)
    # Base: 10x10x4 at origin
    base = trimesh.creation.box(extents=(10, 10, 4))
    base.apply_translation([0, 0, 2])
    
    # Arm: 4x10x10 at x=3
    arm = trimesh.creation.box(extents=(4, 10, 10))
    arm.apply_translation([3, 0, 9]) # z goes from 4 to 14
    
    # Overhang piece extending left from arm: 10x10x4 at z=12
    overhang = trimesh.creation.box(extents=(10, 10, 4))
    overhang.apply_translation([-4, 0, 12]) # z goes from 10 to 14, overhang bottom is at z=10
    
    mesh = trimesh.boolean.union([base, arm, overhang])
    
    # The overhang bottom is at Z=10. min_z is 0. 10 > 0 + 2.0. So it is an overhang.
    planes = AutoSegmenter.compute_segmentation(mesh, enable_auto_segment=True)
    
    assert len(planes) == 2
    
    base_plane = planes[0]
    assert base_plane.unit_normal == (0.0, 0.0, 1.0)
    
    tilted_plane = planes[1]
    assert tilted_plane.plane_origin == (0.0, 0.0, 8.0) # lowest_z (10) - 2.0
    
    # Because overhang extends to the left (-X), tilt direction should be negative X.
    # Therefore, tilt normal should be tilted towards -X.
    # nx = -(-1)*sin45 = sin45 > 0
    assert tilted_plane.unit_normal[0] > 0.0
    assert tilted_plane.unit_normal[2] > 0.0
    
    # Ensure it's 45 degrees
    np.testing.assert_almost_equal(tilted_plane.unit_normal[2], np.cos(np.radians(45.0)))
