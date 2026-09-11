import pytest
import numpy as np
from shapely.geometry import Polygon
from infill_region_classifier import classify_infill_regions

def test_pyramid_step():
    # 10x10 base current layer (area 100)
    current_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # 10x10 prev layer (perfect match, no exposed bottom)
    prev_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # 6x6 next layer from (2,2) to (8,8) (area 36)
    # The roof rim should be area 64
    next_geom = Polygon([[2, 2], [8, 2], [8, 8], [2, 8]])
    
    result = classify_infill_regions(current_geom, prev_geom, next_geom)
    
    solid = result["solid"]
    internal = result["internal"]
    
    assert np.isclose(solid.area, 64.0, atol=1e-3)
    assert np.isclose(internal.area, 36.0, atol=1e-3)

def test_bottom_first_layer():
    # 10x10 base current layer (area 100)
    current_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    # No previous layer! This means the entire area is a floor.
    prev_geom = None
    
    # 10x10 next layer (perfect match, no exposed roof)
    next_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    result = classify_infill_regions(current_geom, prev_geom, next_geom)
    
    solid = result["solid"]
    internal = result["internal"]
    
    assert np.isclose(solid.area, 100.0, atol=1e-3)
    assert np.isclose(internal.area, 0.0, atol=1e-3)

def test_pure_internal():
    # 10x10 straight cylinder
    current_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    prev_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    next_geom = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
    
    result = classify_infill_regions(current_geom, prev_geom, next_geom)
    
    solid = result["solid"]
    internal = result["internal"]
    
    # Everything has support above and below
    assert np.isclose(solid.area, 0.0, atol=1e-3)
    assert np.isclose(internal.area, 100.0, atol=1e-3)

def test_empty_current_layer():
    empty_poly = Polygon()
    result = classify_infill_regions(empty_poly, empty_poly, empty_poly)
    
    assert result["solid"].is_empty
    assert result["internal"].is_empty
