import pytest
import numpy as np
from shapely.geometry import Polygon
from shell_offset import generate_shells

def test_standard_two_shells():
    # Construct a 10x10 square
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # Generate 2 shells with a line width of 1.0
    # First shell should be offset inward by 0.5 (9x9 box)
    # Second shell should be offset inward by 1.5 (7x7 box)
    shells = generate_shells(poly, line_width=1.0, shell_count=2)
    
    assert len(shells) == 2
    
    # 9x9 box perimeter = 4 * 9 = 36.0
    assert np.isclose(shells[0].length, 36.0)
    
    # 7x7 box perimeter = 4 * 7 = 28.0
    assert np.isclose(shells[1].length, 28.0)

def test_empty_offset_handling():
    # Construct a tiny 2x2 square
    poly = Polygon([[0, 0], [2, 0], [2, 2], [0, 2]])
    
    # Generate 5 shells with a line width of 1.0
    # Shell 1: offset 0.5 -> 1x1 box -> succeeds
    # Shell 2: offset 1.5 -> empty polygon -> gracefully exits
    shells = generate_shells(poly, line_width=1.0, shell_count=5)
    
    assert len(shells) == 1
    # 1x1 box perimeter = 4 * 1 = 4.0
    assert np.isclose(shells[0].length, 4.0)

def test_multi_region_splitting():
    # Construct a "dumbbell" shaped polygon
    # Two 5x5 boxes connected by a 1x2 bridge
    # Total bounding box is wider, but the bridge is thin in Y.
    # We will buffer it so the bridge completely disappears, leaving two islands.
    coords = [
        [0, 0], [5, 0], [5, 2], [10, 2], [10, 0], [15, 0],
        [15, 5], [10, 5], [10, 3], [5, 3], [5, 5], [0, 5]
    ]
    poly = Polygon(coords)
    
    # Bridge width is 1.0 (Y goes from 2 to 3)
    # Offset of 0.6 will destroy the bridge but leave the 5x5 blocks (now 3.8 x 3.8)
    shells = generate_shells(poly, line_width=1.2, shell_count=1)
    
    # Because the bridge is severed, 2 islands are created inside the same layer
    assert len(shells) == 2
    
    # Original 5x5 box shrunk by 0.6 => (5 - 1.2) = 3.8 box
    # Perimeter of each is 4 * 3.8 = 15.2
    assert np.isclose(shells[0].length, 15.2)
    assert np.isclose(shells[1].length, 15.2)

def test_invalid_parameters():
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # Zero line width returns empty
    assert len(generate_shells(poly, line_width=0.0, shell_count=2)) == 0
    # Negative shells returns empty
    assert len(generate_shells(poly, line_width=1.0, shell_count=-1)) == 0
