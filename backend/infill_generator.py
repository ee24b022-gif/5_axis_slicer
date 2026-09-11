import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.affinity import rotate
from typing import Union, List

GeometryType = Union[Polygon, MultiPolygon]

def generate_line_infill(
    polygon: GeometryType,
    spacing: float,
    angle_degrees: float
) -> List[LineString]:
    """
    Generates structured alternating line infill by casting 1D linear grids bounded 
    within the topological structure of an abstract polygon boundary.
    
    Args:
        polygon: The target geometric bounding region.
        spacing: The absolute physical spacing between parallel line centers.
        angle_degrees: The rotational angle (Z-axis offset) for the resulting line structures.
        
    Returns:
        List[LineString]: Array of independent 1D physical paths clipped within the bounds.
    """
    if polygon is None or polygon.is_empty or spacing <= 0.0:
        return []

    # Rotation origin defaults to the mathematical center for stability
    origin = polygon.centroid
    
    # 1. Reverse-transform the polygon boundary backward to absolute X/Y coordinate space
    rotated_poly = rotate(polygon, -angle_degrees, origin=origin)
    
    # 2. Extract bounding limits
    minx, miny, maxx, maxy = rotated_poly.bounds
    
    # 3. Cast internal horizontal lines bounded precisely to the local Y limits
    grid_lines = []
    current_y = miny + (spacing / 2.0)
    
    # Prevent infinite loops in edge cases
    if maxy - miny > 100000:
        return []
        
    while current_y <= maxy:
        # Extend the X limits slightly to ensure intersection algorithms never drop exact boundary edge cases
        line = LineString([(minx - 1.0, current_y), (maxx + 1.0, current_y)])
        grid_lines.append(line)
        current_y += spacing
        
    if not grid_lines:
        return []
        
    grid_collection = MultiLineString(grid_lines)
    
    # 4. Execute standard boolean clipping masking out all empty air space
    intersection = grid_collection.intersection(rotated_poly)
    
    if intersection.is_empty:
        return []
        
    # 5. Rotate the surviving physical traces back to absolute world coordinates
    final_lines_geom = rotate(intersection, angle_degrees, origin=origin)
    
    # 6. Unpack anomalous nested Shapely collections safely
    final_lines = []
    
    def extract_lines(geom):
        if geom.geom_type == 'LineString':
            final_lines.append(geom)
        elif geom.geom_type == 'MultiLineString':
            final_lines.extend(list(geom.geoms))
        elif geom.geom_type == 'GeometryCollection':
            for inner_geom in geom.geoms:
                extract_lines(inner_geom)
                
    extract_lines(final_lines_geom)
    
    return final_lines
