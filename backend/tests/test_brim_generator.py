import pytest
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LinearRing
from brim_generator import generate_brim

def test_standard_brim_expansion():
    # 10x10 base
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # 3 brim lines with line_width 1.0
    # Expected expansion offsets: +0.5, +1.5, +2.5
    brims = generate_brim(poly, line_width=1.0, brim_lines=3)
    
    assert len(brims) == 3
    
    # Square lengths: (10 + 2*offset) * 4
    # Brim 1: 10 + 1 = 11 => 44 length
    assert np.isclose(brims[0].length, 44.0)
    # Brim 2: 10 + 3 = 13 => 52 length
    assert np.isclose(brims[1].length, 52.0)
    # Brim 3: 10 + 5 = 15 => 60 length
    assert np.isclose(brims[2].length, 60.0)

def test_brim_ignores_holes():
    # 10x10 box with a 6x6 hole in the center
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]], 
                   holes=[[[2, 2], [8, 2], [8, 8], [2, 8]]])
    
    brims = generate_brim(poly, line_width=1.0, brim_lines=1)
    
    # It should only return 1 brim (the exterior), not 2 (one exterior, one interior)
    assert len(brims) == 1
    
    # And it should strictly match the external expansion length
    assert np.isclose(brims[0].length, 44.0)

def test_island_merging():
    # Two 5x5 blocks sitting 1.0 unit apart from each other
    # Block 1: [0, 5] x [0, 5]
    # Block 2: [6, 11] x [0, 5]
    poly1 = Polygon([[0, 0], [5, 0], [5, 5], [0, 5]])
    poly2 = Polygon([[6, 0], [11, 0], [11, 5], [6, 5]])
    mp = MultiPolygon([poly1, poly2])
    
    # Generating a brim with line_width=1.0
    # First brim line offsets by +0.5. The gap is 1.0. 
    # The left block expands +0.5 right, right block expands +0.5 left. They touch exactly at X=5.5!
    # A tiny buffer > 0.5 merges them completely. Let's do brim line 2 which offsets by 1.5.
    
    brims = generate_brim(mp, line_width=1.0, brim_lines=2)
    
    # The first layer exactly touches at X=5.5, so Shapely merges them immediately into ONE boundary ring!
    # The second layer (offset 1.5) is also ONE ring.
    
    assert len(brims) == 2  # Total = 2 rings.
    
    # Let's verify specifically the last brim is a single ring!
    assert isinstance(brims[-1], LinearRing)

def test_invalid_parameters():
    poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    empty_poly = Polygon()
    
    assert len(generate_brim(empty_poly, 1.0, 3)) == 0
    assert len(generate_brim(poly, 0.0, 3)) == 0
    assert len(generate_brim(poly, 1.0, 0)) == 0
