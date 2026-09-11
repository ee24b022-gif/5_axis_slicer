import numpy as np
import shapely
from shapely.geometry import MultiLineString
from shapely.ops import polygonize, linemerge

segments = np.array([
    [[0.0, 0.0], [1.0, 0.0]],
    [[1.0, 1e-16], [1.0, 1.0]],
    [[1.0, 1.0], [0.0, 1.0]],
    [[0.0, 1.0], [0.0, 0.0]]
])

lines = MultiLineString(list(segments))
print("Original is closed?", getattr(lines, 'is_closed', False))

# Try rounding to precision
lines_snapped = shapely.set_precision(lines, grid_size=1e-8)

merged = linemerge(lines_snapped)
print("Merged is closed?", getattr(merged, 'is_closed', False))

polys = list(polygonize(merged))
print("Polygons found:", len(polys))

