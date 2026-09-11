import numpy as np
from shapely.geometry import MultiLineString
from shapely.ops import polygonize_full

segments = np.array([
    [[0, 0], [10, 0]], [[10, 0], [10, 10]], [[10, 10], [0, 10]], [[0, 10], [0, 0]],
    [[2, 2], [8, 2]], [[8, 2], [8, 8]], [[8, 8], [2, 8]], [[2, 8], [2, 2]]
])

lines = MultiLineString(list(segments))
polygons, dangles, cuts, invalids = polygonize_full(lines)
print(f"Polygonize_full found {len(polygons.geoms)} polygons")
for i, p in enumerate(polygons.geoms):
    print(f"Poly {i} has {len(p.interiors)} holes, area: {p.area}")

