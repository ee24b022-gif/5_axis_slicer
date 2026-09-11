import shapely
from shapely.geometry import Polygon, MultiPolygon, LinearRing
from typing import Union, List

GeometryType = Union[Polygon, MultiPolygon]

def generate_brim(
    slice_geom: GeometryType,
    line_width: float,
    brim_lines: int
) -> List[LinearRing]:
    """
    Constructs an outward-facing structural base adhesion footprint (a brim) safely 
    ignoring internal geometry topologies and merging nearby structural bodies.
    
    Args:
        slice_geom: The raw baseline topology of the part resting on the print bed.
        line_width: The strict geometric extrusion width.
        brim_lines: Total number of concentric outward rings to generate.
        
    Returns:
        List[LinearRing]: The external physical toolpaths.
    """
    shells = []
    
    if slice_geom is None or slice_geom.is_empty or brim_lines <= 0 or line_width <= 0:
        return shells
        
    for i in range(brim_lines):
        # Dynamically push the physical envelope outward.
        # First shell snaps to the mathematical boundary + half the physical filament width.
        offset_distance = (line_width / 2.0) + (i * line_width)
        
        # Buffer outwardly preserving corner integrity
        expanded = slice_geom.buffer(offset_distance, join_style=2)
        
        if expanded.is_empty:
            continue
            
        # Hard-filter exclusively for geometric exteriors 
        # By ignoring .interiors, we prevent the engine from building brims inside topological holes
        if expanded.geom_type == 'Polygon':
            shells.append(expanded.exterior)
        elif expanded.geom_type == 'MultiPolygon':
            for geom in expanded.geoms:
                shells.append(geom.exterior)
                
    return shells
