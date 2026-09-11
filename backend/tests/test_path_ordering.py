import pytest
import numpy as np
from shapely.geometry import LineString
from path_ordering import order_paths

def test_s_curve_weaving():
    # 3 horizontal lines, typically generated bottom to top
    l1 = LineString([(0, 0), (10, 0)])
    l2 = LineString([(0, 2), (10, 2)])
    l3 = LineString([(0, 4), (10, 4)])
    
    # Start at origin
    ordered = order_paths((0, 0), [l1, l2, l3])
    
    assert len(ordered) == 3
    
    # First line should be l1, normal direction (nearest start is 0,0)
    assert list(ordered[0].coords) == [(0.0, 0.0), (10.0, 0.0)]
    
    # Second line should be l2, reversed! 
    # Current head is at (10,0). Nearest endpoint is l2's end (10,2).
    # So it reverses l2 to print from (10,2) to (0,2).
    assert list(ordered[1].coords) == [(10.0, 2.0), (0.0, 2.0)]
    
    # Third line should be l3, normal direction.
    # Current head is at (0,2). Nearest endpoint is l3's start (0,4).
    # So it prints from (0,4) to (10,4).
    assert list(ordered[2].coords) == [(0.0, 4.0), (10.0, 4.0)]

def test_determinism_on_tie():
    # Two identical vertical lines, perfectly symmetric around the start point
    l1 = LineString([(0, 0), (0, 10)])
    l2 = LineString([(10, 0), (10, 10)])
    
    # Start perfectly between their start points at (5,0)
    ordered = order_paths((5, 0), [l1, l2])
    
    assert len(ordered) == 2
    
    # Because of index traversal order (i=0 then i=1 with strictly `<`), 
    # l1 will ALWAYS win a tie against l2.
    assert list(ordered[0].coords) == [(0.0, 0.0), (0.0, 10.0)]
    
    # Re-run passing them backwards to prove the tie follows array order
    ordered_reversed = order_paths((5, 0), [l2, l1])
    assert list(ordered_reversed[0].coords) == [(10.0, 0.0), (10.0, 10.0)]

def test_empty_paths():
    assert len(order_paths((0,0), [])) == 0

def test_handles_empty_linestrings():
    l1 = LineString()
    l2 = LineString([(0, 0), (10, 0)])
    
    ordered = order_paths((0,0), [l1, l2])
    assert len(ordered) == 1
    assert list(ordered[0].coords) == [(0.0, 0.0), (10.0, 0.0)]
