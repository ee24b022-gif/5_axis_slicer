import pytest
import numpy as np
import trimesh.transformations as tf
from transform_utils import restore_segments_to_world

def test_transform_application_round_trip():
    # 1. Mathematically define a tilted plane matrix
    # e.g., translated by (10, 20, 30) and rotated 45 deg around X
    trans = tf.translation_matrix([10.0, 20.0, 30.0])
    rot = tf.rotation_matrix(np.radians(45.0), [1, 0, 0])
    mat = tf.concatenate_matrices(trans, rot)
    flat_matrix = mat.flatten().tolist()
    
    # 2. Synthesize an abstract 2D shape (a square at z_height = 5.0)
    z_height = 5.0
    segments = np.array([
        [[0.0, 0.0], [1.0, 0.0]],
        [[1.0, 0.0], [1.0, 1.0]],
        [[1.0, 1.0], [0.0, 1.0]],
        [[0.0, 1.0], [0.0, 0.0]]
    ], dtype=np.float64) # Shape (4, 2, 2)
    
    # 3. Feed it through the engine
    world_segs = restore_segments_to_world(segments, z_height, flat_matrix)
    
    # 4. Assertions
    assert world_segs.shape == (4, 2, 3)
    
    # Verify the first point (0, 0, 5) locally
    # It goes through mat.
    # [10, 20, 30] + R_x(45) * [0, 0, 5]
    # R_x(45) * [0, 0, 5] = [0, -5*sin(45), 5*cos(45)] = [0, -3.5355, 3.5355]
    # Translated: [10, 16.4645, 33.5355]
    p1 = world_segs[0, 0, :]
    
    cos45 = np.cos(np.radians(45.0))
    sin45 = np.sin(np.radians(45.0))
    
    expected_p1_x = 10.0
    expected_p1_y = 20.0 - 5.0 * sin45
    expected_p1_z = 30.0 + 5.0 * cos45
    
    np.testing.assert_almost_equal(p1[0], expected_p1_x, decimal=4)
    np.testing.assert_almost_equal(p1[1], expected_p1_y, decimal=4)
    np.testing.assert_almost_equal(p1[2], expected_p1_z, decimal=4)

def test_transform_application_empty():
    segments = np.empty((0, 2, 2), dtype=np.float64)
    flat_matrix = np.eye(4).flatten().tolist()
    
    world_segs = restore_segments_to_world(segments, 10.0, flat_matrix)
    assert world_segs.shape == (0, 2, 3)
