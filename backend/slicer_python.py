import math
import struct
import json

class BVHNode:
    __slots__ = ['min_x', 'min_y', 'min_z', 'max_x', 'max_y', 'max_z', 'left', 'right', 'first', 'count']
    def __init__(self):
        self.min_x = self.min_y = self.min_z = 1e9
        self.max_x = self.max_y = self.max_z = -1e9
        self.left = -1
        self.right = -1
        self.first = 0
        self.count = 0

def load_stl(file_bytes):
    if len(file_bytes) < 84:
        raise ValueError("Invalid STL file")
    
    header = file_bytes[:80]
    is_ascii = b"facet normal" in header
    
    triangles = []
    
    if not is_ascii:
        num_triangles = struct.unpack_from("<I", file_bytes, 80)[0]
        offset = 84
        for _ in range(num_triangles):
            if offset + 50 > len(file_bytes):
                break
            data = struct.unpack_from("<12fH", file_bytes, offset)
            nx, ny, nz = data[0:3]
            v0x, v0y, v0z = data[3:6]
            v1x, v1y, v1z = data[6:9]
            v2x, v2y, v2z = data[9:12]
            
            # Recalculate normal if invalid
            if nx*nx + ny*ny + nz*nz < 0.01:
                e1x, e1y, e1z = v1x - v0x, v1y - v0y, v1z - v0z
                e2x, e2y, e2z = v2x - v0x, v2y - v0y, v2z - v0z
                cx = e1y * e2z - e1z * e2y
                cy = e1z * e2x - e1x * e2z
                cz = e1x * e2y - e1y * e2x
                length = math.sqrt(cx*cx + cy*cy + cz*cz)
                if length > 0:
                    nx, ny, nz = cx/length, cy/length, cz/length
                    
            triangles.append((v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, nx, ny, nz))
            offset += 50
    else:
        raise ValueError("ASCII STL not supported in pure Python fallback yet. Please upload a binary STL.")
        
    if not triangles:
        raise ValueError("No triangles found")
        
    # Find bounds
    min_x = min_y = min_z = 1e9
    max_x = max_y = max_z = -1e9
    
    for tri in triangles:
        v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, _, _, _ = tri
        min_x = min(min_x, v0x, v1x, v2x)
        min_y = min(min_y, v0y, v1y, v2y)
        min_z = min(min_z, v0z, v1z, v2z)
        max_x = max(max_x, v0x, v1x, v2x)
        max_y = max(max_y, v0y, v1y, v2y)
        max_z = max(max_z, v0z, v1z, v2z)
        
    # Center mesh
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    cz = min_z
    
    centered_triangles = []
    min_x = min_y = min_z = 1e9
    max_x = max_y = max_z = -1e9
    
    for tri in triangles:
        v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, nx, ny, nz = tri
        v0x -= cx; v0y -= cy; v0z -= cz
        v1x -= cx; v1y -= cy; v1z -= cz
        v2x -= cx; v2y -= cy; v2z -= cz
        centered_triangles.append((v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, nx, ny, nz))
        min_x = min(min_x, v0x, v1x, v2x)
        min_y = min(min_y, v0y, v1y, v2y)
        min_z = min(min_z, v0z, v1z, v2z)
        max_x = max(max_x, v0x, v1x, v2x)
        max_y = max(max_y, v0y, v1y, v2y)
        max_z = max(max_z, v0z, v1z, v2z)
        
    return centered_triangles, (min_x, min_y, min_z), (max_x, max_y, max_z)


def get_z_slice_segments(triangles, z):
    segments = []
    for tri in triangles:
        v = [(tri[0], tri[1], tri[2]), (tri[3], tri[4], tri[5]), (tri[6], tri[7], tri[8])]
        above = [pt for pt in v if pt[2] >= z]
        below = [pt for pt in v if pt[2] < z]
        
        if len(above) == 0 or len(below) == 0:
            continue
            
        pts = []
        for a in above:
            for b in below:
                t = (z - b[2]) / (a[2] - b[2]) if a[2] != b[2] else 0
                ix = b[0] + t * (a[0] - b[0])
                iy = b[1] + t * (a[1] - b[1])
                pts.append((ix, iy))
                
        if len(pts) >= 2:
            segments.append((pts[0], pts[1], tri[9], tri[10], tri[11]))
    return segments

def chain_segments(segments):
    adj = {}
    for i, seg in enumerate(segments):
        p1 = (round(seg[0][0], 3), round(seg[0][1], 3))
        p2 = (round(seg[1][0], 3), round(seg[1][1], 3))
        if p1 not in adj: adj[p1] = []
        if p2 not in adj: adj[p2] = []
        adj[p1].append((p2, i))
        adj[p2].append((p1, i))
        
    visited_seg = set()
    loops = []
    
    for start_p, edges in adj.items():
        for edge in edges:
            if edge[1] in visited_seg: continue
            
            loop = []
            curr_p = start_p
            next_p = edge[0]
            seg_idx = edge[1]
            
            loop.append((curr_p, segments[seg_idx]))
            
            while True:
                visited_seg.add(seg_idx)
                curr_p = next_p
                neighbors = adj.get(curr_p, [])
                next_edge = None
                for n in neighbors:
                    if n[1] not in visited_seg:
                        next_edge = n
                        break
                if not next_edge:
                    break
                next_p = next_edge[0]
                seg_idx = next_edge[1]
                loop.append((curr_p, segments[seg_idx]))
                
            loops.append(loop)
            
    return loops

def generate_infill(segments, min_x, max_x, min_y, max_y, line_width):
    infill_lines = []
    y = min_y
    idx = 0
    while y <= max_y:
        intersects = []
        for seg in segments:
            p1, p2 = seg[0], seg[1]
            if (p1[1] <= y < p2[1]) or (p2[1] <= y < p1[1]):
                t = (y - p1[1]) / (p2[1] - p1[1])
                ix = p1[0] + t * (p2[0] - p1[0])
                intersects.append(ix)
        intersects.sort()
        
        line_pts = []
        for i in range(0, len(intersects)-1, 2):
            x0 = intersects[i]
            x1 = intersects[i+1]
            if idx % 2 != 0:
                line_pts.append((x1, y))
                line_pts.append((x0, y))
            else:
                line_pts.append((x0, y))
                line_pts.append((x1, y))
                
        if line_pts:
            infill_lines.extend(line_pts)
            
        y += line_width
        idx += 1
    return infill_lines

def slice_mesh(file_bytes, layer_height, bed_center_z):
    triangles, min_b, max_b = load_stl(file_bytes)
    min_x, min_y, min_z = min_b
    max_x, max_y, max_z = max_b
    
    if (max_x - min_x) > 500.0 or (max_y - min_y) > 500.0:
        return {"error": "Model is too large (>500mm). Scale down your STL to millimeters to prevent memory crash."}
        
    line_width = 0.4 # Default nozzle line width
    
    path = []
    layer_idx = 0
    
    z = min_z + layer_height
    while z <= max_z:
        segments = get_z_slice_segments(triangles, z)
        if not segments:
            z += layer_height
            layer_idx += 1
            continue
            
        # 1. Perimeters (5-axis tilted)
        loops = chain_segments(segments)
        for loop in loops:
            for pt, seg in loop:
                nx, ny, nz = seg[2], seg[3], seg[4]
                # Force normal to point outwards horizontally somewhat, but keep true 3D normal for tilt
                if nz < 0: nz = -nz # Prevent nozzle from going upside down
                # Avoid completely flat normals to prevent 90 deg violent tilts if not needed
                if nz < 0.1: nz = 0.1 
                length = math.sqrt(nx*nx + ny*ny + nz*nz)
                nx, ny, nz = nx/length, ny/length, nz/length
                path.append((pt[0], pt[1], z, nx, ny, nz, layer_idx, "perimeter"))
                
        # 2. Infill (Straight down)
        infill_pts = generate_infill(segments, min_x, max_x, min_y, max_y, line_width)
        for pt in infill_pts:
            path.append((pt[0], pt[1], z, 0.0, 0.0, 1.0, layer_idx, "infill"))
            
        z += layer_height
        layer_idx += 1
        
    if not path:
        return {"error": "No path generated"}
        
    # Generate GCode
    gcode = []
    gcode.append("; Open5x Volumetric Slicer Output (Python Engine)")
    gcode.append("G21 ; Set units to millimeters")
    gcode.append("G90 ; Absolute positioning")
    gcode.append("M82 ; Absolute extrusion mode")
    gcode.append("G28 ; Home all axes")
    gcode.append("G0 Z50 F3000 ; Move up to avoid collisions")
    
    current_v = 0.0
    current_e = 0.0
    base_feedrate = 1500.0
    e_multiplier = 0.05
    
    last_px = last_py = last_pz = 0.0
    last_mx = last_my = last_mz = last_mu = last_mv = 0.0
    is_first = True
    
    points_json = []
    
    for pt in path:
        px, py, pz, nx, ny, nz, layer, ptype = pt
        points_json.append({"x": round(px, 2), "y": round(py, 2), "z": round(pz, 2), "layer": layer, "type": ptype})
        
        v_rad = math.atan2(nx, ny)
        xy_mag = math.sqrt(nx*nx + ny*ny)
        u_rad = math.atan2(xy_mag, nz)
        
        pz_centered = pz + bed_center_z
        cv, sv = math.cos(v_rad), math.sin(v_rad)
        cu, su = math.cos(u_rad), math.sin(u_rad)
        
        p_rot_x = cv * px - sv * py
        p_rot_y = cu * (sv * px + cv * py) - su * pz_centered
        p_rot_z = su * (sv * px + cv * py) + cu * pz_centered
        
        mx = p_rot_x
        my = p_rot_y
        mz = p_rot_z - bed_center_z
        
        u_deg = u_rad * 180.0 / math.pi
        v_deg = v_rad * 180.0 / math.pi
        
        current_mod = current_v % 360.0
        target_mod = v_deg % 360.0
        
        diff = target_mod - current_mod
        if diff > 180.0: diff -= 360.0
        elif diff < -180.0: diff += 360.0
        
        current_v += diff
        mv = current_v
        mu = u_deg
        
        if is_first:
            gcode.append(f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv:.3f} F3000")
            last_px, last_py, last_pz = px, py, pz
            last_mx, last_my, last_mz, last_mu, last_mv = mx, my, mz, mu, mv
            is_first = False
            continue
            
        dist_part = math.sqrt((px - last_px)**2 + (py - last_py)**2 + (pz - last_pz)**2)
        dist_mach = math.sqrt((mx - last_mx)**2 + (my - last_my)**2 + (mz - last_mz)**2 + (mu - last_mu)**2 + (mv - last_mv)**2)
        
        # If moving to a new layer or jumping across infill, retract and move
        if dist_part > 5.0:
            gcode.append(f"G1 E{current_e - 2.0:.3f} F2400 ; Retract")
            gcode.append(f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv:.3f} F3000")
            gcode.append(f"G1 E{current_e:.3f} F2400 ; Unretract")
            last_px, last_py, last_pz = px, py, pz
            last_mx, last_my, last_mz, last_mu, last_mv = mx, my, mz, mu, mv
            continue
        
        current_e += dist_part * e_multiplier
        feedrate = base_feedrate * (dist_mach / dist_part) if dist_part > 0 else base_feedrate
        if feedrate > 6000.0: feedrate = 6000.0
        
        gcode.append(f"G1 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv:.3f} E{current_e:.3f} F{feedrate:.1f}")
        
        last_px, last_py, last_pz = px, py, pz
        last_mx, last_my, last_mz, last_mu, last_mv = mx, my, mz, mu, mv
        
    return {
        "toolpath_points": points_json,
        "gcode": "\\n".join(gcode) + "\\n"
    }
