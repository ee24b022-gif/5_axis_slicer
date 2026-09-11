import shapely
from shapely.geometry import Polygon, MultiPolygon, LinearRing
from typing import Union, List

def generate_shells(
    slice_geom: Union[Polygon, MultiPolygon], 
    line_width: float, 
    shell_count: int
) -> List[LinearRing]:
    """
    Algorithmically generates physical 2D machine toolpaths for outer perimeter walls 
    by shrinking the absolute mathematical polygon bounds inward.
    
    Args:
        slice_geom (Polygon | MultiPolygon): The mathematically ideal 2D slice boundary.
        line_width (float): The physical 3D printer extrusion width.
        shell_count (int): The total number of solid perimeter walls to generate.
        
    Returns:
        List[LinearRing]: Array of connected topological boundaries representing toolpaths.
    """
    shells = []
    
    if shell_count <= 0 or line_width <= 0:
        return shells
        
    if slice_geom.geom_type == 'Polygon':
        target_geometries = [slice_geom]
    elif slice_geom.geom_type == 'MultiPolygon':
        target_geometries = list(slice_geom.geoms)
    else:
        return shells
        
    for i in range(shell_count):
        # Calculate exactly how far into the geometry the tool nozzle center must rest
        # First shell is offset by exactly 1/2 of line_width
        # Subsequent shells are offset by another full line_width 
        offset_distance = (line_width / 2.0) + (i * line_width)
        
        valid_shrunk_geometries = []
        
        for geom in target_geometries:
            # MITRE join style (2) preserves sharp 90-degree outer corners. 
            # Negative buffer implies shrinking the polygon computationally inwards.
            shrunk = geom.buffer(-offset_distance, join_style=2)
            
            if shrunk.is_empty:
                continue
                
            if shrunk.geom_type == 'Polygon':
                valid_shrunk_geometries.append(shrunk)
            elif shrunk.geom_type == 'MultiPolygon':
                valid_shrunk_geometries.extend(list(shrunk.geoms))
                
        # If no geometries survived the inward buffer constraint, geometry is exhausted
        if not valid_shrunk_geometries:
            break
            
        # Extract traversable boundaries
        for p in valid_shrunk_geometries:
            shells.append(p.exterior)
            for interior in p.interiors:
                shells.append(interior)
                
    return shells
