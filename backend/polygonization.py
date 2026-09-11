import numpy as np
import shapely
from shapely.geometry import MultiLineString, LinearRing, Polygon, MultiPolygon
from shapely.ops import linemerge
from shapely.validation import make_valid

def reconstruct_polygons(segments: np.ndarray, precision: float = 1e-5) -> MultiPolygon:
    """
    Transforms N x 2 x 2 unstructured line segments into valid Shapely topological geometries.
    
    Extracts the line direction inherently stored from the 3D triangles, using the 
    winding order (CCW = Solid, CW = Hole) to intelligently reconstruct nested shapes dynamically.
    
    Args:
        segments (np.ndarray): Unstructured line segments of shape (N, 2, 2).
        precision (float): Coordinate tolerance to snap floating-point drift closures.
        
    Returns:
        MultiPolygon: The validated, watertight 2D polygonal slice layer.
    """
    if len(segments) == 0:
        return MultiPolygon()
        
    # Snap micro-gaps inherently using Shapely
    lines = MultiLineString(list(segments))
    lines_snapped = shapely.set_precision(lines, grid_size=precision)
    
    # Merge continuously adjacent segments into long LineStrings
    merged = linemerge(lines_snapped)
    
    if merged.geom_type == 'LineString':
        geoms = [merged]
    elif merged.geom_type == 'MultiLineString':
        geoms = merged.geoms
    else:
        geoms = []
        
    outers = []
    inners = []
    
    # Segregate bounds purely mathematically based on winding direction
    for line in geoms:
        if line.is_closed:
            # LinearRing checks the exact enclosed topological area orientation
            ring = LinearRing(line.coords)
            if ring.is_ccw:
                outers.append(ring)
            else:
                inners.append(ring)
        # Non-closed lines can be skipped as invalid layer diagnostics later
                
    polys = []
    for out in outers:
        poly_bound = Polygon(out)
        # Find which inner holes sit explicitly inside this specific outer bounding contour
        holes = [inn for inn in inners if poly_bound.contains(Polygon(inn))]
        
        # Instantiate polygon with matched holes
        solid = Polygon(out, holes=holes)
        
        # Self-intersecting crossing tangencies inherently produce an invalid state 
        # (e.g. figure-8 loops). make_valid magically untangles these into MultiPolygons.
        if not solid.is_valid:
            solid = make_valid(solid)
            
        if solid.geom_type == 'Polygon':
            polys.append(solid)
        elif solid.geom_type == 'MultiPolygon':
            polys.extend(list(solid.geoms))
        elif solid.geom_type == 'GeometryCollection':
            for geom in solid.geoms:
                if geom.geom_type == 'Polygon':
                    polys.append(geom)
                elif geom.geom_type == 'MultiPolygon':
                    polys.extend(list(geom.geoms))

    return MultiPolygon(polys)
