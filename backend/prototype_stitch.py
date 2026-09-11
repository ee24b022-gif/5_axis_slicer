import numpy as np
from shapely.geometry import MultiLineString, LinearRing, Polygon
from shapely.ops import linemerge
import shapely

# A CCW square (outer) and a CW square (inner)
segments = np.array([
    # Outer CCW
    [[0, 0], [10, 0]], [[10, 0], [10, 10]], [[10, 10], [0, 10]], [[0, 10], [0, 0]],
    # Inner CW
    [[2, 2], [2, 8]], [[2, 8], [8, 8]], [[8, 8], [8, 2]], [[8, 2], [2, 2]]
])

lines = MultiLineString(list(segments))
lines = shapely.set_precision(lines, 1e-6)
merged = linemerge(lines)

if merged.geom_type == 'LineString':
    merged = [merged]
else:
    merged = merged.geoms

outers = []
inners = []

for line in merged:
    if line.is_closed:
        ring = LinearRing(line.coords)
        if ring.is_ccw:
            outers.append(ring)
        else:
            inners.append(ring)

print(f"Outers: {len(outers)}, Inners: {len(inners)}")

# Construct polygons
polys = []
for out in outers:
    poly = Polygon(out)
    holes = [inn for inn in inners if poly.contains(Polygon(inn))]
    polys.append(Polygon(out, holes=holes))

for i, p in enumerate(polys):
    print(f"Poly {i} area: {p.area}")

