import shapely
from shapely.geometry import Polygon, LineString, MultiLineString
from shapely.affinity import rotate
import math

def generate_line_infill(polygon, spacing: float, angle_degrees: float):
    if polygon.is_empty:
        return []
        
    # Rotate the polygon to align the desired fill lines with the X axis (horizontal)
    # We rotate by -angle so horizontal lines will become angled when rotated back
    center = polygon.centroid
    rotated_poly = rotate(polygon, -angle_degrees, origin=center)
    
    # Get bounds
    minx, miny, maxx, maxy = rotated_poly.bounds
    
    # Generate horizontal lines
    lines = []
    y = miny + (spacing / 2.0)
    while y <= maxy:
        # Create a line slightly wider than the bounds just to be safe
        line = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
        lines.append(line)
        y += spacing
        
    if not lines:
        return []
        
    # Create a MultiLineString of all grid lines
    grid = MultiLineString(lines)
    
    # Clip grid against the rotated polygon
    intersection = grid.intersection(rotated_poly)
    
    # If the intersection is empty, return
    if intersection.is_empty:
        return []
        
    # Rotate the intersection lines back by +angle
    final_lines_geom = rotate(intersection, angle_degrees, origin=center)
    
    # Extract line strings
    final_lines = []
    if final_lines_geom.geom_type == 'LineString':
        final_lines.append(final_lines_geom)
    elif final_lines_geom.geom_type == 'MultiLineString':
        final_lines.extend(list(final_lines_geom.geoms))
    elif final_lines_geom.geom_type == 'GeometryCollection':
        for geom in final_lines_geom.geoms:
            if geom.geom_type == 'LineString':
                final_lines.append(geom)
            elif geom.geom_type == 'MultiLineString':
                final_lines.extend(list(geom.geoms))
                
    return final_lines

poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
lines = generate_line_infill(poly, spacing=2.0, angle_degrees=45.0)

for l in lines:
    print(f"Line from {l.coords[0]} to {l.coords[1]}, length {l.length}")
