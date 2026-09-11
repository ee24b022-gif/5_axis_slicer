import shapely
from shapely.geometry import Polygon

poly = Polygon([[0, 0], [10, 0], [10, 10], [0, 10]])
# join_style 2 is MITRE
shrunk = poly.buffer(-0.5, join_style=2)
print("Shrunk area:", shrunk.area)
print("Boundary length:", shrunk.exterior.length)

