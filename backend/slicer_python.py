import math
import struct
import json
import array
import tempfile


class BranchNode:
    def __init__(self, pt):
        self.pt = pt
        self.children = []
        self.depth = 0

class Branch:
    def __init__(self):
        self.pts = []

def point_in_polygon(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
    return inside

class BVHNode:
    __slots__ = ['min_x', 'min_y', 'min_z', 'max_x', 'max_y', 'max_z', 'left', 'right', 'first', 'count']
    def __init__(self):
        self.min_x = self.min_y = self.min_z = 1e9
        self.max_x = self.max_y = self.max_z = -1e9
        self.left = -1
        self.right = -1
        self.first = 0
        self.count = 0

def load_stl(file_bytes, model_scale=1.0, rot_x=0.0, rot_y=0.0, rot_z=0.0, pos_x=0.0, pos_y=0.0):
    if len(file_bytes) < 84:
        raise ValueError("Invalid STL file")
    
    header = file_bytes[:80]
    is_ascii = b"facet normal" in header
    
    triangles = []
    
    if not is_ascii:
        num_triangles = struct.unpack_from("<I", file_bytes, 80)[0]
        offset = 84
        for _ in range(num_triangles):
            if offset + 50 > len(file_bytes): break
            data = struct.unpack_from("<12fH", file_bytes, offset)
            nx, ny, nz = data[0:3]
            v0x, v0y, v0z = data[3:6]
            v1x, v1y, v1z = data[6:9]
            v2x, v2y, v2z = data[9:12]
            
            if nx*nx + ny*ny + nz*nz < 0.01:
                e1x, e1y, e1z = v1x - v0x, v1y - v0y, v1z - v0z
                e2x, e2y, e2z = v2x - v0x, v2y - v0y, v2z - v0z
                cx = e1y * e2z - e1z * e2y
                cy = e1z * e2x - e1x * e2z
                cz = e1x * e2y - e1y * e2x
                length = math.sqrt(cx*cx + cy*cy + cz*cz)
                if length > 0: nx, ny, nz = cx/length, cy/length, cz/length
                    
            triangles.append((v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, nx, ny, nz))
            offset += 50
    else:
        raise ValueError("ASCII STL not supported in pure Python fallback yet. Please upload a binary STL.")
        
    if not triangles:
        raise ValueError("No triangles found")
        
    min_x = min_y = min_z = 1e9
    max_x = max_y = max_z = -1e9
    for tri in triangles:
        min_x = min(min_x, tri[0], tri[3], tri[6])
        min_y = min(min_y, tri[1], tri[4], tri[7])
        min_z = min(min_z, tri[2], tri[5], tri[8])
        max_x = max(max_x, tri[0], tri[3], tri[6])
        max_y = max(max_y, tri[1], tri[4], tri[7])
        max_z = max(max_z, tri[2], tri[5], tri[8])
        
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    cz = (min_z + max_z) / 2.0
    
    rad_x = rot_x * math.pi / 180.0
    rad_y = rot_y * math.pi / 180.0
    rad_z = rot_z * math.pi / 180.0
    
    cx_x = math.cos(rad_x); sx_x = math.sin(rad_x)
    cy_y = math.cos(rad_y); sy_y = math.sin(rad_y)
    cz_z = math.cos(rad_z); sz_z = math.sin(rad_z)
    
    transformed_triangles = []
    t_min_x = t_min_y = t_min_z = 1e9
    t_max_x = t_max_y = t_max_z = -1e9
    
    def apply_transform(x, y, z):
        x -= cx; y -= cy; z -= cz
        x *= model_scale; y *= model_scale; z *= model_scale
        y1 = y * cx_x - z * sx_x
        z1 = y * sx_x + z * cx_x
        x2 = x * cy_y + z1 * sy_y
        z2 = -x * sy_y + z1 * cy_y
        x3 = x2 * cz_z - y1 * sz_z
        y3 = x2 * sz_z + y1 * cz_z
        return x3, y3, z2
        
    def apply_transform_normal(nx, ny, nz):
        ny1 = ny * cx_x - nz * sx_x
        nz1 = ny * sx_x + nz * cx_x
        nx2 = nx * cy_y + nz1 * sy_y
        nz2 = -nx * sy_y + nz1 * cy_y
        nx3 = nx2 * cz_z - ny1 * sz_z
        ny3 = nx2 * sz_z + ny1 * cz_z
        l = math.sqrt(nx3*nx3 + ny3*ny3 + nz2*nz2)
        if l > 0: return nx3/l, ny3/l, nz2/l
        return nx3, ny3, nz2

    for tri in triangles:
        v0x, v0y, v0z = apply_transform(tri[0], tri[1], tri[2])
        v1x, v1y, v1z = apply_transform(tri[3], tri[4], tri[5])
        v2x, v2y, v2z = apply_transform(tri[6], tri[7], tri[8])
        nx, ny, nz = apply_transform_normal(tri[9], tri[10], tri[11])
        
        t_min_z = min(t_min_z, v0z, v1z, v2z)
        transformed_triangles.append([v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, nx, ny, nz])
        
    final_triangles = []
    f_min_x = f_min_y = f_min_z = 1e9
    f_max_x = f_max_y = f_max_z = -1e9
    
    for tri in transformed_triangles:
        tri[0] += pos_x; tri[1] += pos_y; tri[2] -= t_min_z
        tri[3] += pos_x; tri[4] += pos_y; tri[5] -= t_min_z
        tri[6] += pos_x; tri[7] += pos_y; tri[8] -= t_min_z
        
        f_min_x = min(f_min_x, tri[0], tri[3], tri[6])
        f_min_y = min(f_min_y, tri[1], tri[4], tri[7])
        f_min_z = min(f_min_z, tri[2], tri[5], tri[8])
        f_max_x = max(f_max_x, tri[0], tri[3], tri[6])
        f_max_y = max(f_max_y, tri[1], tri[4], tri[7])
        f_max_z = max(f_max_z, tri[2], tri[5], tri[8])
        
        final_triangles.append(tuple(tri))
        
    return final_triangles, (f_min_x, f_min_y, f_min_z), (f_max_x, f_max_y, f_max_z)


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

def generate_infill(segments, min_x, max_x, min_y, max_y, line_width, pattern="lines", layer_idx=0):
    infill_lines = []
    
    def generate_axis_infill(is_x_axis):
        axis_lines = []
        v_start = min_y if is_x_axis else min_x
        v_end = max_y if is_x_axis else max_x
            
        v = v_start
        idx = 0
        while v <= v_end:
            intersects = []
            for seg in segments:
                p1, p2 = seg[0], seg[1]
                if is_x_axis:
                    if (p1[1] <= v < p2[1]) or (p2[1] <= v < p1[1]):
                        t = (v - p1[1]) / (p2[1] - p1[1])
                        ix = p1[0] + t * (p2[0] - p1[0])
                        intersects.append(ix)
                else:
                    if (p1[0] <= v < p2[0]) or (p2[0] <= v < p1[0]):
                        t = (v - p1[0]) / (p2[0] - p1[0])
                        iy = p1[1] + t * (p2[1] - p1[1])
                        intersects.append(iy)
            intersects.sort()
            
            line_pts = []
            for i in range(0, len(intersects)-1, 2):
                v0 = intersects[i]
                v1 = intersects[i+1]
                
                if idx % 2 != 0:
                    if is_x_axis:
                        line_pts.extend([(v1, v), (v0, v)])
                    else:
                        line_pts.extend([(v, v1), (v, v0)])
                else:
                    if is_x_axis:
                        line_pts.extend([(v0, v), (v1, v)])
                    else:
                        line_pts.extend([(v, v0), (v, v1)])
                    
            if line_pts:
                axis_lines.extend(line_pts)
                
            v += line_width
            idx += 1
        return axis_lines

    if pattern == "grid":
        infill_lines.extend(generate_axis_infill(True))
        infill_lines.extend(generate_axis_infill(False))
    else:
        if layer_idx % 2 == 0:
            infill_lines.extend(generate_axis_infill(True))
        else:
            infill_lines.extend(generate_axis_infill(False))
            
    return infill_lines
                
def slice_mesh(file_bytes, layer_height, bed_center_z, wave_amplitude=0.0, wave_frequency=0.1, infill_density=20.0, auto_segment=False, model_scale=1.0, rot_x=0.0, rot_y=0.0, rot_z=0.0, pos_x=0.0, pos_y=0.0, infill_pattern="lines", support_enabled=True, support_angle=45.0, support_density=15.0, support_z_gap=0.2, auto_segment_threshold=5.0):
    original_triangles, min_b, max_b = load_stl(file_bytes, model_scale, rot_x, rot_y, rot_z, pos_x, pos_y)
    
    processed_triangles = []
    
    fade_height = 15.0
    
    def get_attenuation(z):
        if z <= 0.0: return 0.0
        if z >= fade_height: return 1.0
        return z / fade_height
    
    def distort_mesh_z(x, y, z):
        wave = wave_amplitude * math.sin(wave_frequency * x) * math.cos(wave_frequency * y)
        return z - get_attenuation(z) * wave
        
    def distort_toolpath_z(x, y, z_dist):
        wave = wave_amplitude * math.sin(wave_frequency * x) * math.cos(wave_frequency * y)
        if z_dist <= 0.0:
            return z_dist
        
        # Calculate what z_dist would be exactly at fade_height
        z_dist_fade = fade_height - wave
        
        if z_dist >= z_dist_fade:
            return z_dist + wave
            
        # In the linear fade zone, z_dist = z_orig - (z_orig / fade_height) * wave
        # Solve for z_orig: z_orig = z_dist / (1.0 - wave / fade_height)
        denom = 1.0 - (wave / fade_height)
        if denom <= 0.01: # Prevent division by zero if amplitude >= fade_height
            return z_dist + wave
            
        return z_dist / denom
        
    def get_wavy_normal(x, y, true_z):
        if wave_amplitude == 0.0:
            return 0.0, 0.0, 1.0
            
        att = get_attenuation(true_z)
        if att == 0.0:
            return 0.0, 0.0, 1.0
            
        df_dx = att * wave_amplitude * wave_frequency * math.cos(wave_frequency * x) * math.cos(wave_frequency * y)
        df_dy = -att * wave_amplitude * wave_frequency * math.sin(wave_frequency * x) * math.sin(wave_frequency * y)
        nx, ny, nz = -df_dx, -df_dy, 1.0
        length = math.sqrt(nx*nx + ny*ny + nz*nz)
        return nx/length, ny/length, nz/length

    def resample_pts(p1, p2, max_len=0.5):
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        d = math.hypot(dx, dy)
        if d <= max_len:
            return [p1, p2]
        n = int(math.ceil(d / max_len))
        pts = []
        for i in range(n + 1):
            t = i / n
            pts.append((p1[0] + dx*t, p1[1] + dy*t))
        return pts

    def subdivide_triangles(triangles, max_len=2.0):
        if wave_amplitude == 0.0:
            return triangles
            
        def edge_len(a, b): return math.hypot(math.hypot(a[0]-b[0], a[1]-b[1]), a[2]-b[2])
        
        result = []
        stack = list(triangles)
        
        while stack:
            tri = stack.pop()
            v0, v1, v2 = (tri[0], tri[1], tri[2]), (tri[3], tri[4], tri[5]), (tri[6], tri[7], tri[8])
            n = (tri[9], tri[10], tri[11])
            
            l01 = edge_len(v0, v1)
            l12 = edge_len(v1, v2)
            l20 = edge_len(v2, v0)
            
            max_l = max(l01, l12, l20)
            if max_l <= max_len:
                result.append((*v0, *v1, *v2, *n))
            elif max_l == l01:
                vm = ((v0[0]+v1[0])/2, (v0[1]+v1[1])/2, (v0[2]+v1[2])/2)
                stack.append((*v0, *vm, *v2, *n))
                stack.append((*vm, *v1, *v2, *n))
            elif max_l == l12:
                vm = ((v1[0]+v2[0])/2, (v1[1]+v2[1])/2, (v1[2]+v2[2])/2)
                stack.append((*v0, *v1, *vm, *n))
                stack.append((*v0, *vm, *v2, *n))
            else:
                vm = ((v2[0]+v0[0])/2, (v2[1]+v0[1])/2, (v2[2]+v0[2])/2)
                stack.append((*v0, *v1, *vm, *n))
                stack.append((*vm, *v1, *v2, *n))
                
        return result
        
    subdivided_triangles = subdivide_triangles(original_triangles, max_len=2.0)
    
    min_x, min_y, min_z = min_b
    max_x, max_y, max_z = max_b
    
    calc_z_cutoff = 1e9
    calc_segment_tilt = 0.0
    t_min_z = min_z
    

    # Skeleton-driven conformal slicing
    path = slice_skeleton_mesh_inner(original_triangles, layer_height, infill_density, infill_pattern)
    
    if not path:
        return {"error": "No path generated"}
    points_json = {
        "x": array.array('f'),
        "y": array.array('f'),
        "z": array.array('f'),
        "nx": array.array('f'),
        "ny": array.array('f'),
        "nz": array.array('f'),
        "layer": array.array('H'),
        "type": array.array('B'),
        "path_id": array.array('I')
    }
    
    gcode_file = tempfile.TemporaryFile(mode='w+')
    gcode_file.write("; Open5x Volumetric Slicer Output (Python Engine)\\n")
    gcode_file.write("G21 ; Set units to millimeters\\n")
    gcode_file.write("G90 ; Absolute positioning\\n")
    gcode_file.write("M82 ; Absolute extrusion mode\\n")
    gcode_file.write("G28 ; Home all axes\\n")
    gcode_file.write("G0 Z50 F3000 ; Move up to avoid collisions\\n")
    
    current_v = 0.0
    current_e = 0.0
    base_feedrate = 1500.0
    e_multiplier = 0.05
    
    last_px = last_py = last_pz = 0.0
    last_mx = last_my = last_mz = last_mu = last_mv = 0.0
    is_first = True
    last_path_id = -1
    
    for pt in path:
        px, py, pz, nx, ny, nz, layer, ptype, current_path_id = pt
        points_json["x"].append(px)
        points_json["y"].append(py)
        points_json["z"].append(pz)
        points_json["nx"].append(nx)
        points_json["ny"].append(ny)
        points_json["nz"].append(nz)
        points_json["layer"].append(layer)
        points_json["type"].append(0 if ptype == "perimeter" else (2 if ptype == "support" else 1))
        points_json["path_id"].append(current_path_id)
        
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
            gcode_file.write(f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv:.3f} F3000\\n")
            last_px, last_py, last_pz = px, py, pz
            last_mx, last_my, last_mz, last_mu, last_mv = mx, my, mz, mu, mv
            last_path_id = current_path_id
            is_first = False
            continue
            
        dist_part = math.sqrt((px - last_px)**2 + (py - last_py)**2 + (pz - last_pz)**2)
        dist_mach = math.sqrt((mx - last_mx)**2 + (my - last_my)**2 + (mz - last_mz)**2 + (mu - last_mu)**2 + (mv - last_mv)**2)
        
        # If moving to a new layer, jumping across infill, or jumping across cutoff gaps, retract and move
        if dist_part > 1.5 or current_path_id != last_path_id:
            gcode_file.write(f"G1 E{current_e - 2.0:.3f} F2400 ; Retract\\n")
            gcode_file.write(f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv:.3f} F3000\\n")
            gcode_file.write(f"G1 E{current_e:.3f} F2400 ; Unretract\\n")
            last_px, last_py, last_pz = px, py, pz
            last_mx, last_my, last_mz, last_mu, last_mv = mx, my, mz, mu, mv
            last_path_id = current_path_id
            continue
        
        current_e += dist_part * e_multiplier
        feedrate = base_feedrate * (dist_mach / dist_part) if dist_part > 0 else base_feedrate
        if feedrate > 6000.0: feedrate = 6000.0
        
        gcode_file.write(f"G1 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv:.3f} E{current_e:.3f} F{feedrate:.1f}\\n")
        
        last_px, last_py, last_pz = px, py, pz
        last_mx, last_my, last_mz, last_mu, last_mv = mx, my, mz, mu, mv
        
    gcode_file.flush()
    return {
        "toolpath_points": points_json,
        "gcode_file": gcode_file,
        "segmentation_info": {
            "auto_segment": auto_segment,
            "calc_z_cutoff": round(calc_z_cutoff, 2) if calc_z_cutoff != 1e9 else "None",
            "calc_segment_tilt": round(calc_segment_tilt, 2)
        }
    }


def extract_skeleton(triangles, min_z, max_z, dz=1.0):
    import array
    t_mins = array.array('f', [0] * len(triangles))
    t_maxs = array.array('f', [0] * len(triangles))
    for i, t in enumerate(triangles):
        t_mins[i] = min(t[2], t[5], t[8])
        t_maxs[i] = max(t[2], t[5], t[8])
            
    layers = []
    z = min_z + dz
    while z <= max_z:
        layer_tris = []
        for i in range(len(triangles)):
            if t_mins[i] <= z and t_maxs[i] >= z:
                t = triangles[i]
                layer_tris.append((t_mins[i], t_maxs[i], t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8], t[9], t[10], t[11]))
                
        segments = get_z_slice_segments(layer_tris, z)
        
        loops = chain_segments(segments)
        centroids = []
        for loop in loops:
            cx, cy = 0.0, 0.0
            area = 0.0
            pts = [seg[0] for seg in loop]
            for i in range(len(pts)):
                j = (i + 1) % len(pts)
                cross = pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
                area += cross
                cx += (pts[i][0] + pts[j][0]) * cross
                cy += (pts[i][1] + pts[j][1]) * cross
            
            area *= 0.5
            if area != 0:
                cx /= (6.0 * area)
                cy /= (6.0 * area)
                centroids.append((cx, cy, z))
            else:
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                centroids.append((cx, cy, z))
                
        if centroids:
            layers.append(centroids)
        z += dz
        
    return layers

def build_tree(layers):
    if not layers: return []
    roots = [BranchNode(c) for c in layers[0]]
    prev_nodes = roots
    
    for centroids in layers[1:]:
        current_nodes = [BranchNode(c) for c in centroids]
        for cn in current_nodes:
            closest_pn = min(prev_nodes, key=lambda pn: math.dist(pn.pt, cn.pt))
            closest_pn.children.append(cn)
        prev_nodes = current_nodes
        
    for r in roots:
        calculate_depths(r)
    return roots

def calculate_depths(node):
    if not node.children:
        node.depth = 1
        return 1
    max_d = 0
    for c in node.children:
        d = calculate_depths(c)
        max_d = max(max_d, d)
    node.depth = max_d + 1
    return node.depth

def extract_branches(node, current_branch, branches):
    current_branch.pts.append(node.pt)
    if not node.children:
        return
        
    children = sorted(node.children, key=lambda c: c.depth, reverse=True)
    extract_branches(children[0], current_branch, branches)
    
    for child in children[1:]:
        new_branch = Branch()
        new_branch.pts.append(node.pt) 
        branches.append(new_branch)
        extract_branches(child, new_branch, branches)

def intersect_mesh_plane(triangles, P, N):
    segments = []
    nx, ny, nz = N
    px, py, pz = P
    
    for t in triangles:
        d0 = (t[0] - px)*nx + (t[1] - py)*ny + (t[2] - pz)*nz
        d1 = (t[3] - px)*nx + (t[4] - py)*ny + (t[5] - pz)*nz
        d2 = (t[6] - px)*nx + (t[7] - py)*ny + (t[8] - pz)*nz
        
        if (d0 > 0 and d1 > 0 and d2 > 0) or (d0 < 0 and d1 < 0 and d2 < 0):
            continue
            
        pts = []
        if (d0 > 0) != (d1 > 0) or (d0 == 0 and d1 != 0):
            denom = d0 - d1
            if denom != 0:
                t_val = d0 / denom
                pts.append((t[0] + t_val*(t[3]-t[0]), t[1] + t_val*(t[4]-t[1]), t[2] + t_val*(t[5]-t[2])))
        if (d1 > 0) != (d2 > 0) or (d1 == 0 and d2 != 0):
            denom = d1 - d2
            if denom != 0:
                t_val = d1 / denom
                pts.append((t[3] + t_val*(t[6]-t[3]), t[4] + t_val*(t[7]-t[4]), t[5] + t_val*(t[8]-t[5])))
        if (d2 > 0) != (d0 > 0) or (d2 == 0 and d0 != 0):
            denom = d2 - d0
            if denom != 0:
                t_val = d2 / denom
                pts.append((t[6] + t_val*(t[0]-t[6]), t[7] + t_val*(t[1]-t[7]), t[8] + t_val*(t[2]-t[8])))
                
        unique_pts = []
        for p in pts:
            is_dup = False
            for up in unique_pts:
                if abs(p[0]-up[0]) < 1e-5 and abs(p[1]-up[1]) < 1e-5 and abs(p[2]-up[2]) < 1e-5:
                    is_dup = True; break
            if not is_dup: unique_pts.append(p)
                
        if len(unique_pts) == 2:
            segments.append((unique_pts[0], unique_pts[1], t[9], t[10], t[11]))
            
    return segments

def get_local_frame(N):
    nx, ny, nz = N
    if abs(nz) < 0.9:
        ux, uy, uz = 0, 0, 1
    else:
        ux, uy, uz = 1, 0, 0
        
    Ux = ny*uz - nz*uy
    Uy = nz*ux - nx*uz
    Uz = nx*uy - ny*ux
    
    u_len = math.sqrt(Ux*Ux + Uy*Uy + Uz*Uz)
    if u_len == 0:
        Ux, Uy, Uz = 1.0, 0.0, 0.0
    else:
        Ux, Uy, Uz = Ux/u_len, Uy/u_len, Uz/u_len
    
    Vx = ny*Uz - nz*Uy
    Vy = nz*Ux - nx*Uz
    Vz = nx*Uy - ny*Ux
    
    return (Ux, Uy, Uz), (Vx, Vy, Vz)

def resample_polyline(pts, max_len=0.5):
    if not pts: return []
    resampled = [pts[0]]
    for i in range(len(pts)-1):
        p1, p2 = pts[i], pts[i+1]
        dx, dy, dz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
        d = math.sqrt(dx*dx + dy*dy + dz*dz)
        if d <= max_len:
            resampled.append(p2)
        else:
            steps = int(math.ceil(d / max_len))
            for s in range(1, steps + 1):
                t = s / steps
                resampled.append((p1[0] + dx * t, p1[1] + dy * t, p1[2] + dz * t))
    return resampled

def slice_skeleton_mesh_inner(triangles, layer_height, infill_density, infill_pattern):
    path = []
    
    # 1. Extract skeleton
    min_z = min(min(t[2], t[5], t[8]) for t in triangles)
    max_z = max(max(t[2], t[5], t[8]) for t in triangles)
    layers = extract_skeleton(triangles, min_z, max_z, dz=0.5)
    
    roots = build_tree(layers)
    branches = []
    for root in roots:
        b = Branch()
        branches.append(b)
        extract_branches(root, b, branches)
        
    layer_idx = 0
    path_id = 0
    line_width = 0.4
    infill_spacing = line_width / (infill_density / 100.0) if infill_density > 0.1 else 1e9
    
    # Precompute min/max for infill
    min_x = min(min(t[0], t[3], t[6]) for t in triangles)
    max_x = max(max(t[0], t[3], t[6]) for t in triangles)
    min_y = min(min(t[1], t[4], t[7]) for t in triangles)
    max_y = max(max(t[1], t[4], t[7]) for t in triangles)
    
    for branch in branches:
        pts = resample_polyline(branch.pts, layer_height)
        if len(pts) < 2: continue
        
        # Calculate tangents
        for i in range(len(pts)):
            if i == 0:
                dx = pts[1][0] - pts[0][0]
                dy = pts[1][1] - pts[0][1]
                dz = pts[1][2] - pts[0][2]
            elif i == len(pts) - 1:
                dx = pts[-1][0] - pts[-2][0]
                dy = pts[-1][1] - pts[-2][1]
                dz = pts[-1][2] - pts[-2][2]
            else:
                dx = pts[i+1][0] - pts[i-1][0]
                dy = pts[i+1][1] - pts[i-1][1]
                dz = pts[i+1][2] - pts[i-1][2]
                
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            if length == 0:
                nx, ny, nz = 0, 0, 1
            else:
                nx, ny, nz = dx/length, dy/length, dz/length
                
            # Restrict tangents from pointing downwards during printing (overhang limit)
            if nz < 0:
                nz = 0.0
                length = math.sqrt(nx*nx + ny*ny + nz*nz)
                nx, ny, nz = nx/length, ny/length, nz/length
            
            P = pts[i]
            N = (nx, ny, nz)
            
            # Slice with plane
            segments = intersect_mesh_plane(triangles, P, N)
            loops = chain_segments(segments)
            if not loops: continue
            
            # Convert to local 2D frame to filter
            U, V = get_local_frame(N)
            
            best_loop = None
            best_dist = 1e9
            
            local_loops = []
            for loop in loops:
                local_pts = []
                for seg in loop:
                    p3d = seg[0]
                    u = (p3d[0]-P[0])*U[0] + (p3d[1]-P[1])*U[1] + (p3d[2]-P[2])*U[2]
                    v = (p3d[0]-P[0])*V[0] + (p3d[1]-P[1])*V[1] + (p3d[2]-P[2])*V[2]
                    local_pts.append((u, v))
                local_loops.append(local_pts)
                
                if point_in_polygon(0, 0, local_pts):
                    best_loop = loop
                    break
                else:
                    # Find closest loop if none contain center
                    for pu, pv in local_pts:
                        d = math.hypot(pu, pv)
                        if d < best_dist:
                            best_dist = d
                            best_loop = loop
                            
            if best_loop:
                # Add Perimeter
                path_id += 1
                for seg in best_loop:
                    p3d = seg[0]
                    path.append((p3d[0], p3d[1], p3d[2], nx, ny, nz, layer_idx, "perimeter", path_id))
                path.append((best_loop[0][0][0], best_loop[0][0][1], best_loop[0][0][2], nx, ny, nz, layer_idx, "perimeter", path_id))
                
                # Generate Infill
                # We need local 2D segments for generate_infill
                local_segments = []
                for seg in best_loop:
                    p1 = seg[0]
                    p2 = seg[1]
                    u1 = (p1[0]-P[0])*U[0] + (p1[1]-P[1])*U[1] + (p1[2]-P[2])*U[2]
                    v1 = (p1[0]-P[0])*V[0] + (p1[1]-P[1])*V[1] + (p1[2]-P[2])*V[2]
                    u2 = (p2[0]-P[0])*U[0] + (p2[1]-P[1])*U[1] + (p2[2]-P[2])*U[2]
                    v2 = (p2[0]-P[0])*V[0] + (p2[1]-P[1])*V[1] + (p2[2]-P[2])*V[2]
                    local_segments.append(((u1, v1), (u2, v2)))
                    
                infill_pts = generate_infill(local_segments, -500, 500, -500, 500, infill_spacing, infill_pattern, layer_idx)
                for i_pt in range(0, len(infill_pts), 2):
                    p1 = infill_pts[i_pt]
                    p2 = infill_pts[i_pt+1]
                    # Map back to 3D
                    x1 = P[0] + p1[0]*U[0] + p1[1]*V[0]
                    y1 = P[1] + p1[0]*U[1] + p1[1]*V[1]
                    z1 = P[2] + p1[0]*U[2] + p1[1]*V[2]
                    x2 = P[0] + p2[0]*U[0] + p2[1]*V[0]
                    y2 = P[1] + p2[0]*U[1] + p2[1]*V[1]
                    z2 = P[2] + p2[0]*U[2] + p2[1]*V[2]
                    
                    path_id += 1
                    path.append((x1, y1, z1, nx, ny, nz, layer_idx, "infill", path_id))
                    path.append((x2, y2, z2, nx, ny, nz, layer_idx, "infill", path_id))
                    
            layer_idx += 1
            
    return path
