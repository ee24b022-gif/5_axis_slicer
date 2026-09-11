import shapely
from shapely.geometry import Polygon

def classify_regions(current, prev_geom, next_geom):
    # What is not covered by next layer is a Top surface
    top_exposed = current.difference(next_geom) if next_geom and not next_geom.is_empty else current
    
    # What is not covered by prev layer is a Bottom surface
    bottom_exposed = current.difference(prev_geom) if prev_geom and not prev_geom.is_empty else current
    
    # Combine them for solid infill
    solid_infill = top_exposed.union(bottom_exposed)
    
    # The rest is internal sparse infill
    internal_infill = current.difference(solid_infill)
    
    return {
        "solid": solid_infill,
        "internal": internal_infill
    }

c = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
p = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
n = Polygon([[2, 2], [8, 2], [8, 8], [2, 8]]) # Smaller next layer (pyramid)

res = classify_regions(c, p, n)
print("Solid area:", res["solid"].area)
print("Internal area:", res["internal"].area)
