import shapely
from shapely.geometry import Polygon, MultiPolygon
from typing import Union, Dict, Optional

GeometryType = Union[Polygon, MultiPolygon]

def classify_infill_regions(
    current_geom: GeometryType,
    prev_geom: Optional[GeometryType],
    next_geom: Optional[GeometryType]
) -> Dict[str, GeometryType]:
    """
    Classifies a 2D slice boundary into solid and internal regions based on vertical adjacency.
    
    Any part of the current geometry that has no support below it (prev_geom) is a floor.
    Any part of the current geometry that has no structure above it (next_geom) is a roof.
    Floors and roofs form the solid infill mask. The remainder is internal sparse infill.
    
    Args:
        current_geom: The bounding geometry of the current layer.
        prev_geom: The bounding geometry of the layer directly beneath, or None if first layer.
        next_geom: The bounding geometry of the layer directly above, or None if last layer.
        
    Returns:
        Dict[str, GeometryType]: Dictionary containing "solid" and "internal" geometry masks.
    """
    
    if current_geom is None or current_geom.is_empty:
        empty = Polygon()
        return {"solid": empty, "internal": empty}

    # Identify Roofs (exposed top surfaces)
    if next_geom is None or next_geom.is_empty:
        top_exposed = current_geom
    else:
        top_exposed = current_geom.difference(next_geom)
        
    # Identify Floors (exposed bottom surfaces)
    if prev_geom is None or prev_geom.is_empty:
        bottom_exposed = current_geom
    else:
        bottom_exposed = current_geom.difference(prev_geom)
        
    # Solid infill is the union of all exposed tops and bottoms
    solid_infill = top_exposed.union(bottom_exposed)
    
    # Clean up infinitesimal topological anomalies from shapely booleans
    solid_infill = solid_infill.buffer(1e-6).buffer(-1e-6)
    
    # Internal infill is whatever is left over
    internal_infill = current_geom.difference(solid_infill)
    
    # Same micro-cleanup
    internal_infill = internal_infill.buffer(1e-6).buffer(-1e-6)
    
    return {
        "solid": solid_infill,
        "internal": internal_infill
    }
