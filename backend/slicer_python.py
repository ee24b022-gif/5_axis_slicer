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


def get_z_slice_segments(active_triangles, z):
    segments = []
    for tri in active_triangles:
        pts = []
        for b_idx in (4, 7, 10):
            bz = tri[b_idx]
            if bz < z:
                for a_idx in (4, 7, 10):
                    az = tri[a_idx]
                    if az >= z:
                        dz = az - bz
                        if dz == 0: continue
                        t = (z - bz) / dz
                        ix = tri[b_idx-2] + t * (tri[a_idx-2] - tri[b_idx-2])
                        iy = tri[b_idx-1] + t * (tri[a_idx-1] - tri[b_idx-1])
                        pts.append((ix, iy))
        if len(pts) >= 2:
            segments.append((pts[0], pts[1], tri[11], tri[12], tri[13]))
    return segments

def chain_segments(segments):
    loops = []
    pt_map = {}
    
    def get_key(pt):
        return (round(pt[0], 3), round(pt[1], 3))
        
    for i, seg in enumerate(segments):
        k0 = get_key(seg[0])
        k1 = get_key(seg[1])
        if k0 not in pt_map: pt_map[k0] = []
        if k1 not in pt_map: pt_map[k1] = []
        pt_map[k0].append(i)
        pt_map[k1].append(i)
        
    used = set()
    for start_idx in range(len(segments)):
        if start_idx in used: continue
        
        current_loop = [segments[start_idx]]
        used.add(start_idx)
        last_k = get_key(segments[start_idx][1])
        
        while True:
            found = False
            if last_k in pt_map:
                for next_idx in pt_map[last_k]:
                    if next_idx not in used:
                        seg = segments[next_idx]
                        used.add(next_idx)
                        k0 = get_key(seg[0])
                        k1 = get_key(seg[1])
                        
                        if k0 == last_k:
                            current_loop.append(seg)
                            last_k = k1
                        else:
                            current_loop.append((seg[1], seg[0], seg[2], seg[3], seg[4]))
                            last_k = k0
                        found = True
                        break
            if not found: break
        loops.append(current_loop)
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
                
def slice_mesh(file_bytes, layer_height, bed_center_z, wave_amplitude=0.0, wave_frequency=0.1, infill_density=20.0):
    original_triangles, min_b, max_b = load_stl(file_bytes)
    
    distorted_triangles = []
    dist_min_z, dist_max_z = 1e9, -1e9
    
    def distort_z(x, y, z):
        return z + wave_amplitude * math.sin(wave_frequency * x) * math.cos(wave_frequency * y)
        
    def undistort_z(x, y, z):
        return z - wave_amplitude * math.sin(wave_frequency * x) * math.cos(wave_frequency * y)
        
    def get_wavy_normal(x, y):
        if wave_amplitude == 0.0:
            return 0.0, 0.0, 1.0
        df_dx = wave_amplitude * wave_frequency * math.cos(wave_frequency * x) * math.cos(wave_frequency * y)
        df_dy = -wave_amplitude * wave_frequency * math.sin(wave_frequency * x) * math.sin(wave_frequency * y)
        nx, ny, nz = -df_dx, -df_dy, 1.0
        length = math.sqrt(nx*nx + ny*ny + nz*nz)
        return nx/length, ny/length, nz/length

    for tri in original_triangles:
        v0x, v0y, v0z = tri[0], tri[1], tri[2]
        v1x, v1y, v1z = tri[3], tri[4], tri[5]
        v2x, v2y, v2z = tri[6], tri[7], tri[8]
        
        dv0z = distort_z(v0x, v0y, v0z)
        dv1z = distort_z(v1x, v1y, v1z)
        dv2z = distort_z(v2x, v2y, v2z)
        
        dist_min_z = min(dist_min_z, dv0z, dv1z, dv2z)
        dist_max_z = max(dist_max_z, dv0z, dv1z, dv2z)
        
        distorted_triangles.append((min(dv0z, dv1z, dv2z), max(dv0z, dv1z, dv2z), v0x, v0y, dv0z, v1x, v1y, dv1z, v2x, v2y, dv2z, tri[9], tri[10], tri[11]))

    min_x, min_y, min_z = min_b
    max_x, max_y, max_z = max_b
    
    if (max_x - min_x) > 500.0 or (max_y - min_y) > 500.0:
        return {"error": "Model is too large (>500mm). Scale down your STL to millimeters to prevent memory crash."}
        
    line_width = 0.4 # Default nozzle line width
    if infill_density <= 0.1:
        infill_spacing = 1e9 # effectively no infill
    else:
        infill_spacing = line_width / (infill_density / 100.0)
    
    path = []
    layer_idx = 0
    
    z = dist_min_z + layer_height
    while z <= dist_max_z:
        active_triangles = [t for t in distorted_triangles if t[0] <= z and t[1] >= z]
        segments = get_z_slice_segments(active_triangles, z)
        if not segments:
            z += layer_height
            layer_idx += 1
            continue
            
        # 1. Perimeters (5-axis tilted)
        loops = chain_segments(segments)
        for loop in loops:
            for pt, seg in loop:
                true_z = undistort_z(pt[0], pt[1], z)
                nx, ny, nz = get_wavy_normal(pt[0], pt[1])
                path.append((pt[0], pt[1], true_z, nx, ny, nz, layer_idx, "perimeter"))
                
        # 2. Infill (Straight down or wavy)
        infill_pts = generate_infill(segments, min_x, max_x, min_y, max_y, infill_spacing)
        for pt in infill_pts:
            true_z = undistort_z(pt[0], pt[1], z)
            nx, ny, nz = get_wavy_normal(pt[0], pt[1])
            path.append((pt[0], pt[1], true_z, nx, ny, nz, layer_idx, "infill"))
            
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
