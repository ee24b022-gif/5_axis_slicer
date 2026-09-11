import numpy as np
from shapely.geometry import MultiLineString
from shapely.ops import polygonize

segments = np.array([
    [[0, 0], [10, 0]], [[10, 0], [10, 10]], [[10, 10], [0, 10]], [[0, 10], [0, 0]],
    [[2, 2], [8, 2]], [[8, 2], [8, 8]], [[8, 8], [2, 8]], [[2, 8], [2, 2]]
])

lines = MultiLineString(list(segments))
polys = list(polygonize(lines))
for i, p in enumerate(polys):
    print(f"Poly {i} has {len(p.interiors)} holes, area: {p.area}")
