import pytest
import numpy as np
from polygonization import reconstruct_polygons

def test_winding_order_holes():
    # Construct a CCW outer box and a CW inner hole
    # Outer (10x10) - Area = 100
    outer = [
        [[0, 0], [10, 0]], [[10, 0], [10, 10]], [[10, 10], [0, 10]], [[0, 10], [0, 0]]
    ]
    # Inner (6x6) - Area = 36
    inner = [
        [[2, 2], [2, 8]], [[2, 8], [8, 8]], [[8, 8], [8, 2]], [[8, 2], [2, 2]]
    ]
    
    segments = np.array(outer + inner)
    
    multipoly = reconstruct_polygons(segments)
    
    # It should detect EXACTLY 1 solid polygon with 1 hole
    assert len(multipoly.geoms) == 1
    poly = multipoly.geoms[0]
    
    assert len(poly.interiors) == 1
    # Area = 100 - 36 = 64
    assert np.isclose(poly.area, 64.0)

def test_precision_closure():
    # Gap injected: [10, 0] does not exactly match [10, 1e-6]
    segments = np.array([
        [[0, 0], [10, 0]],
        [[10, 1e-6], [10, 10]],
        [[10, 10], [0, 10]],
        [[0, 10], [0, 0]]
    ])
    
    multipoly = reconstruct_polygons(segments, precision=1e-5)
    
    # 1e-5 precision > 1e-6 gap, so it should securely snap closed
    assert len(multipoly.geoms) == 1
    assert multipoly.geoms[0].is_valid
    
    # If precision is too small, it should fail to close
    multipoly_fail = reconstruct_polygons(segments, precision=1e-8)
    # The LineString isn't closed, so it skips the ring creation
    assert len(multipoly_fail.geoms) == 0

def test_tangent_self_intersections():
    # A figure 8 shape overlapping at (5, 5). 
    # Starts at 0,0 -> 10,10 -> 0,10 -> 10,0 -> 0,0
    # Actually wait, CCW rules are strict for this to be valid. 
    # Let's make a known self-intersecting path.
    segments = np.array([
        [[0, 0], [10, 10]],
        [[10, 10], [0, 10]],
        [[0, 10], [10, 0]],
        [[10, 0], [0, 0]]
    ])
    
    multipoly = reconstruct_polygons(segments)
    
    # make_valid should break the figure-8 into two distinct triangles
    assert len(multipoly.geoms) == 2
    
    # The two triangles have area 25 each
    assert np.isclose(multipoly.geoms[0].area, 25.0)
    assert np.isclose(multipoly.geoms[1].area, 25.0)

def test_empty_segments():
    empty_segments = np.zeros((0, 2, 2))
    multipoly = reconstruct_polygons(empty_segments)
    assert len(multipoly.geoms) == 0
