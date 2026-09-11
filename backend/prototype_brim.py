import shapely
from shapely.geometry import Polygon

def generate_brim(slice_geom, line_width, brim_lines):
    shells = []
    if slice_geom is None or slice_geom.is_empty or brim_lines <= 0:
        return shells
        
    for i in range(brim_lines):
        # We offset OUTWARDS by a positive distance
        dist = (line_width / 2.0) + (i * line_width)
        
        expanded = slice_geom.buffer(dist, join_style=2)
        
        # We want the OUTER BOUNDARY of this expanded polygon.
        # But wait, if the part has holes (interiors), buffering outwards shrinks the holes.
        # Typically brim is only for the exterior footprint (to hold the part down).
        # We should only take the exteriors!
        if expanded.geom_type == 'Polygon':
            shells.append(expanded.exterior)
        elif expanded.geom_type == 'MultiPolygon':
            for geom in expanded.geoms:
                shells.append(geom.exterior)
                
    return shells

poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]], holes=[[[2, 2], [8, 2], [8, 8], [2, 8]]])
print("Original area:", poly.area)

brims = generate_brim(poly, 1.0, 3)
for b in brims:
    print("Brim length:", b.length)
