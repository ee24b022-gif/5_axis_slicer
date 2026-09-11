import math
from shapely.geometry import LineString
from typing import List, Tuple

def order_paths(
    start_pt: Tuple[float, float], 
    paths: List[LineString]
) -> List[LineString]:
    """
    Executes greedy nearest-neighbor geometric ordering for disjoint path structures,
    optionally reversing linear paths dynamically to minimize non-printing travel distance.
    
    Args:
        start_pt: The absolute starting (X, Y) toolhead position.
        paths: A set of unorganized LineString vectors requiring execution.
        
    Returns:
        List[LineString]: The optimized path execution sequence.
    """
    ordered = []
    unprinted = list(paths)
    current_pt = start_pt
    
    if not unprinted:
        return ordered
        
    while unprinted:
        best_idx = -1
        best_dist = float('inf')
        best_reverse = False
        
        for i, path in enumerate(unprinted):
            if path.is_empty:
                continue
                
            coords = list(path.coords)
            if not coords:
                continue
                
            start = coords[0]
            end = coords[-1]
            
            # Distance from current nozzle head to the physical start of this path
            d_start = math.hypot(start[0] - current_pt[0], start[1] - current_pt[1])
            # Distance from current nozzle head to the physical end of this path (requiring reversal)
            d_end = math.hypot(end[0] - current_pt[0], end[1] - current_pt[1])
            
            # Greedy absolute evaluation strictly enforces tie determinism by index processing order
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reverse = False
                
            if d_end < best_dist:
                best_dist = d_end
                best_idx = i
                best_reverse = True
                
        if best_idx == -1:
            # Drop malformed empty structures immediately rather than infinitely looping
            unprinted.pop(0)
            continue
            
        best_path = unprinted.pop(best_idx)
        
        if best_reverse:
            # Physically flip the canonical array structure 
            best_path = LineString(list(best_path.coords)[::-1])
            
        ordered.append(best_path)
        
        # Advance the physical state coordinate to wherever the nozzle stops printing
        current_pt = best_path.coords[-1]
        
    return ordered
