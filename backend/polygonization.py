import numpy as np
import shapely
from shapely.geometry import MultiLineString, LinearRing, Polygon, MultiPolygon
from shapely.ops import linemerge, polygonize
from shapely.validation import make_valid

def reconstruct_polygons(segments: np.ndarray, precision: float = 1e-5) -> MultiPolygon:
    """
    Transforms N x 2 x 2 unstructured line segments into valid Shapely topological geometries.

    Uses nesting depth (not winding direction) to determine exterior vs hole:
    depth 0,2,4... = solid exterior; depth 1,3,5... = hole.

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

    # Collect all closed rings (winding direction is irrelevant)
    rings = []
    for line in geoms:
        if line.is_closed:
            rings.append(LinearRing(line.coords))

    # Polygonize uses nesting depth, not winding, to assign exterior vs hole
    polys = list(polygonize(rings))

    # Handle self-intersecting rings that polygonize couldn't decompose
    for ring in rings:
        poly = Polygon(ring.coords)
        if not poly.is_valid:
            fixed = make_valid(poly)
            if fixed.geom_type == 'MultiPolygon':
                polys.extend(list(fixed.geoms))
            elif fixed.geom_type == 'Polygon':
                polys.append(fixed)

    # Filter by nesting depth: even depth (0,2,4...) = solid, odd depth (1,3,5...) = hole
    # A polygon's depth = how many other polygons' exteriors contain its representative point
    solids = []
    for p in polys:
        point = p.representative_point()
        depth = 0
        for other in polys:
            if other is not p:
                exterior_poly = Polygon(other.exterior)
                if exterior_poly.contains(point):
                    depth += 1
        if depth % 2 == 0:
            solids.append(p)

    # Filter by area and boolean-union into a clean MultiPolygon
    clean = [p for p in solids if p.area > 1e-6]

    if not clean:
        return MultiPolygon()

    union = clean[0]
    for p in clean[1:]:
        union = union.union(p)

    if isinstance(union, MultiPolygon):
        return union
    elif isinstance(union, Polygon):
        return MultiPolygon([union])

    return MultiPolygon()
