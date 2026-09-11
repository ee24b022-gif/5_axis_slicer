import pytest
import numpy as np
from shapely.geometry import Polygon
from infill_generator import generate_line_infill

def test_horizontal_infill():
    # 10x10 square
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # 0 degree angle = horizontal lines
    lines = generate_line_infill(poly, spacing=2.0, angle_degrees=0.0)
    
    # y = 1, 3, 5, 7, 9 -> 5 lines
    assert len(lines) == 5
    
    # All lines should span exactly the width of the box (10.0)
    for line in lines:
        assert np.isclose(line.length, 10.0)

def test_angled_infill():
    # 10x10 square
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # 45 degree angle -> diagonal lines
    lines = generate_line_infill(poly, spacing=2.0, angle_degrees=45.0)
    
    assert len(lines) > 0
    
    # Find the maximum line length
    max_len = max([line.length for line in lines])
    
    # The maximum length should be less than or equal to the bounding box diagonal (sqrt(10^2 + 10^2) = 14.14)
    assert max_len <= np.sqrt(200.0) + 1e-3

def test_multi_region_clipping():
    # C-shaped polygon
    # Left spine (0-2 x 0-10)
    # Top arm (2-10 x 8-10)
    # Bottom arm (2-10 x 0-2)
    coords = [
        [0, 0], [10, 0], [10, 2], [2, 2],
        [2, 8], [10, 8], [10, 10], [0, 10]
    ]
    poly = Polygon(coords)
    
    # Send horizontal lines (angle 0) at spacing 10
    # Wait, spacing 10 with offset 5 will hit y=5.
    # y=5 only intersects the left spine!
    # Let's hit y=1 which intersects the bottom arm, or y=9 which intersects top arm.
    # To test clipping breaking a line into TWO lines, we need vertical lines!
    # Vertical lines (angle 90). Let's use spacing 2.0.
    # The centroid will be used for rotation, but effectively we cast vertical lines.
    # A vertical line at X=8 should intersect the top arm and bottom arm, missing the middle gap.
    
    lines = generate_line_infill(poly, spacing=2.0, angle_degrees=90.0)
    
    # With a 10x10 bounding box and spacing 2.0, we get multiple lines.
    # Since the gap exists from y=2 to y=8 for x>2, vertical lines in that range must split!
    # We should have more total line segments than grid lines because some break in half.
    # Grid lines cast: 5 (x=1, 3, 5, 7, 9)
    # x=1 is solid (0 to 10). (1 line)
    # x=3 is broken (0-2 and 8-10). (2 lines)
    # x=5 is broken. (2 lines)
    # x=7 is broken. (2 lines)
    # x=9 is broken. (2 lines)
    # Total lines: 1 + 2 + 2 + 2 + 2 = 9 lines!
    
    assert len(lines) == 9
    
    # Verify that the sum of lengths equals area / spacing roughly, but more importantly none of the lines are in the gap
    for line in lines:
        for x, y in line.coords:
            # If x > 2, y cannot be strictly between 2 and 8
            if x > 2.01:
                assert y <= 2.01 or y >= 7.99

def test_invalid_parameters():
    empty_poly = Polygon()
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    assert len(generate_line_infill(empty_poly, 1.0, 45.0)) == 0
    assert len(generate_line_infill(poly, 0.0, 45.0)) == 0
