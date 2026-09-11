import shapely
from shapely.geometry import LineString, Point
import math

def order_paths(start_pt, paths):
    ordered = []
    unprinted = list(paths)
    current_pt = start_pt
    
    while unprinted:
        best_idx = -1
        best_dist = float('inf')
        best_reverse = False
        
        for i, path in enumerate(unprinted):
            start = path.coords[0]
            end = path.coords[-1]
            
            d_start = math.hypot(start[0] - current_pt[0], start[1] - current_pt[1])
            d_end = math.hypot(end[0] - current_pt[0], end[1] - current_pt[1])
            
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reverse = False
                
            if d_end < best_dist:
                best_dist = d_end
                best_idx = i
                best_reverse = True
                
        # To maintain determinism on exact distance ties, Python's iteration order
        # naturally picks the first one encountered since we use strictly `<`.
        # So it is deterministic based on input order.
        
        best_path = unprinted.pop(best_idx)
        if best_reverse:
            # Reverse coords
            best_path = LineString(list(best_path.coords)[::-1])
            
        ordered.append(best_path)
        current_pt = best_path.coords[-1]
        
    return ordered

l1 = LineString([(0, 0), (10, 0)])
l2 = LineString([(0, 2), (10, 2)])
l3 = LineString([(0, 4), (10, 4)])

ordered = order_paths((0,0), [l1, l2, l3])
for l in ordered:
    print(list(l.coords))
