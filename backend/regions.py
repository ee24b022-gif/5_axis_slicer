import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, MultiLineString
from shapely.ops import linemerge, polygonize
from typing import List, Tuple

class AreaLogic:
    def __init__(self, extrusion_width: float = 0.4):
        self.extrusion_width = extrusion_width

    def build_polygons_from_segments(self, segments: List[Tuple[Tuple[float, float, float], Tuple[float, float, float]]]) -> List[Polygon]:
        """
        Takes raw 3D segments (where Z is constant) and builds closed 2D polygons.
        Returns a list of valid Shapely Polygons representing the layer boundary.
        """
        # Convert to 2D lines
        lines = [LineString([(s[0][0], s[0][1]), (s[1][0], s[1][1])]) for s in segments]
        
        # Merge connected lines
        merged = linemerge(lines)
        
        # Extract polygons
        # polygonize handles both clean rings and intersecting spaghetti, 
        # but for sliced sections from a watertight mesh, it should yield clean rings.
        polygons = list(polygonize(merged))
        
        # Buffer slightly to heal tiny gaps (1 micrometer), then buffer back
        clean_polys = []
        for p in polygons:
            if not p.is_valid:
                p = p.buffer(0)
            if p.area > 1e-6:
                clean_polys.append(p)
                
        # Merge overlapping polygons just in case (boolean union)
        if clean_polys:
            union_poly = clean_polys[0]
            for p in clean_polys[1:]:
                union_poly = union_poly.union(p)
                
            if isinstance(union_poly, MultiPolygon):
                return list(union_poly.geoms)
            elif isinstance(union_poly, Polygon):
                return [union_poly]
                
        return []

    def generate_shells_and_infill_area(self, boundaries: List[Polygon], num_shells: int = 2) -> Tuple[List[Polygon], List[Polygon]]:
        """
        Takes boundary polygons and generates inset shells (perimeters) and the remaining internal area for infill.
        Returns:
            shells: List of Polygons representing the perimeters (from outer to inner)
            infill_area: List of Polygons representing the area where infill should be generated
        """
        shells = []
        current_area = boundaries
        
        for shell_idx in range(num_shells):
            # Inset by extrusion_width / 2 for the first shell to center the nozzle on the boundary,
            # then full extrusion_width for subsequent shells.
            offset_dist = -(self.extrusion_width / 2.0) if shell_idx == 0 else -self.extrusion_width
            
            next_area = []
            for poly in current_area:
                # Buffer negative shrinks the polygon
                inset = poly.buffer(offset_dist)
                if not inset.is_empty:
                    if isinstance(inset, MultiPolygon):
                        for geom in inset.geoms:
                            if geom.area > 1e-6:
                                shells.append(geom)
                                next_area.append(geom)
                    elif isinstance(inset, Polygon):
                        if inset.area > 1e-6:
                            shells.append(inset)
                            next_area.append(inset)
            
            current_area = next_area
            
        # The remaining area for infill needs to be offset inwards one more half-extrusion width
        # so infill doesn't overlap the innermost shell.
        infill_area = []
        for poly in current_area:
            infill_bound = poly.buffer(-self.extrusion_width)
            if not infill_bound.is_empty:
                if isinstance(infill_bound, MultiPolygon):
                    for geom in infill_bound.geoms:
                        if geom.area > 1e-6:
                            infill_area.append(geom)
                elif isinstance(infill_bound, Polygon):
                    if infill_bound.area > 1e-6:
                        infill_area.append(infill_bound)
                        
        return shells, infill_area

    def generate_infill_lines(self, infill_areas: List[Polygon], spacing: float, angle_deg: float) -> List[LineString]:
        """
        Generates parallel infill lines clipped to the infill_areas.
        """
        if not infill_areas:
            return []
            
        # Determine the bounding box of all infill areas
        minx, miny, maxx, maxy = infill_areas[0].bounds
        for poly in infill_areas[1:]:
            bx, by, cx, cy = poly.bounds
            minx = min(minx, bx); miny = min(miny, by)
            maxx = max(maxx, cx); maxy = max(maxy, cy)
            
        # Expand bounds slightly to ensure full coverage
        diagonal = np.hypot(maxx - minx, maxy - miny)
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        
        # Generate lines centered at (cx, cy)
        angle_rad = np.radians(angle_deg)
        dir_x, dir_y = np.cos(angle_rad), np.sin(angle_rad)
        perp_x, perp_y = -dir_y, dir_x
        
        lines = []
        # Go from -diagonal to +diagonal
        n_lines = int(np.ceil(diagonal / spacing))
        for i in range(-n_lines, n_lines + 1):
            offset = i * spacing
            px = cx + perp_x * offset
            py = cy + perp_y * offset
            
            start = (px - dir_x * diagonal, py - dir_y * diagonal)
            end = (px + dir_x * diagonal, py + dir_y * diagonal)
            lines.append(LineString([start, end]))
            
        multi_line = MultiLineString(lines)
        
        clipped_lines = []
        for poly in infill_areas:
            intersection = multi_line.intersection(poly)
            if intersection.is_empty:
                continue
            if isinstance(intersection, LineString):
                clipped_lines.append(intersection)
            elif isinstance(intersection, MultiLineString):
                for geom in intersection.geoms:
                    clipped_lines.append(geom)
                    
        return clipped_lines
