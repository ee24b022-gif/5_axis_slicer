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


def build_bvh(triangles):
    tri_indices = list(range(len(triangles)))
    tri_bounds = []
    
    for i, tri in enumerate(triangles):
        v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, _, _, _ = tri
        bx_min = min(v0x, v1x, v2x)
        by_min = min(v0y, v1y, v2y)
        bz_min = min(v0z, v1z, v2z)
        bx_max = max(v0x, v1x, v2x)
        by_max = max(v0y, v1y, v2y)
        bz_max = max(v0z, v1z, v2z)
        tri_bounds.append((bx_min, by_min, bz_min, bx_max, by_max, bz_max))
        
    bvh = [BVHNode()]
    bvh[0].first = 0
    bvh[0].count = len(triangles)
    
    def update_bounds(node_idx):
        node = bvh[node_idx]
        for i in range(node.first, node.first + node.count):
            idx = tri_indices[i]
            b = tri_bounds[idx]
            node.min_x = min(node.min_x, b[0])
            node.min_y = min(node.min_y, b[1])
            node.min_z = min(node.min_z, b[2])
            node.max_x = max(node.max_x, b[3])
            node.max_y = max(node.max_y, b[4])
            node.max_z = max(node.max_z, b[5])

    def split_node(node_idx):
        update_bounds(node_idx)
        node = bvh[node_idx]
        if node.count <= 4:
            return
            
        ex = node.max_x - node.min_x
        ey = node.max_y - node.min_y
        ez = node.max_z - node.min_z
        
        axis = 0
        if ey > ex: axis = 1
        if ez > ey and ez > ex: axis = 2
        
        split_pos = node.min_x + ex / 2.0
        if axis == 1: split_pos = node.min_y + ey / 2.0
        if axis == 2: split_pos = node.min_z + ez / 2.0
        
        i = node.first
        j = i + node.count - 1
        
        while i <= j:
            idx = tri_indices[i]
            b = tri_bounds[idx]
            center = (b[axis] + b[axis + 3]) / 2.0
            if center < split_pos:
                i += 1
            else:
                tri_indices[i], tri_indices[j] = tri_indices[j], tri_indices[i]
                j -= 1
                
        left_count = i - node.first
        if left_count == 0 or left_count == node.count:
            # Fallback to object median
            left_count = node.count // 2
            sub_indices = tri_indices[node.first : node.first + node.count]
            sub_indices.sort(key=lambda idx: (tri_bounds[idx][axis] + tri_bounds[idx][axis + 3]) / 2.0)
            tri_indices[node.first : node.first + node.count] = sub_indices
            i = node.first + left_count
            
        node_first = node.first
        node_count = node.count
        
        left_node_idx = len(bvh)
        bvh.append(BVHNode())
        right_node_idx = len(bvh)
        bvh.append(BVHNode())
        
        # Need to re-fetch node because append might reallocate (though not in Python, but good practice)
        bvh[node_idx].left = left_node_idx
        bvh[node_idx].right = right_node_idx
        bvh[node_idx].count = 0
        
        bvh[left_node_idx].first = node_first
        bvh[left_node_idx].count = left_count
        bvh[right_node_idx].first = i
        bvh[right_node_idx].count = node_count - left_count
        
        split_node(left_node_idx)
        split_node(right_node_idx)

    split_node(0)
    return bvh, tri_indices

def ray_triangle_intersect(ox, oy, oz, v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z):
    # Dir is always [0, 0, -1]
    e1x = v1x - v0x
    e1y = v1y - v0y
    e1z = v1z - v0z
    
    e2x = v2x - v0x
    e2y = v2y - v0y
    e2z = v2z - v0z
    
    # pvec = dir.cross(e2)
    # dir = (0, 0, -1) -> pvec = (y*e2z - z*e2y, z*e2x - x*e2z, x*e2y - y*e2x)
    # dir = (0,0,-1) -> pvec = (0 - (-1)*e2y, (-1)*e2x - 0, 0)
    pvecx = e2y
    pvecy = -e2x
    pvecz = 0.0
    
    det = e1x * pvecx + e1y * pvecy + e1z * pvecz
    if -1e-8 < det < 1e-8:
        return False, 0.0
        
    inv_det = 1.0 / det
    tvecx = ox - v0x
    tvecy = oy - v0y
    tvecz = oz - v0z
    
    u = (tvecx * pvecx + tvecy * pvecy + tvecz * pvecz) * inv_det
    if u < 0.0 or u > 1.0:
        return False, 0.0
        
    qvecx = tvecy * e1z - tvecz * e1y
    qvecy = tvecz * e1x - tvecx * e1z
    qvecz = tvecx * e1y - tvecy * e1x
    
    # v = dir.dot(qvec) -> (0,0,-1).dot(qvec) = -qvecz
    v = -qvecz * inv_det
    if v < 0.0 or u + v > 1.0:
        return False, 0.0
        
    t = (e2x * qvecx + e2y * qvecy + e2z * qvecz) * inv_det
    if t > 1e-8:
        return True, t
    return False, 0.0

def slice_mesh(file_bytes, line_width, y_step, bed_center_z):
    triangles, min_b, max_b = load_stl(file_bytes)
    min_x, min_y, min_z = min_b
    max_x, max_y, max_z = max_b
    
    if (max_x - min_x) > 500.0 or (max_y - min_y) > 500.0:
        return {"error": "Model is too large (>500mm). Scale down your STL to millimeters to prevent memory crash."}
        
    bvh, tri_indices = build_bvh(triangles)
    
    path = []
    z_start = max_z + 10.0
    line_idx = 0
    
    x = min_x
    while x <= max_x:
        y_pts = []
        y = min_y
        while y <= max_y:
            y_pts.append(y)
            y += y_step
            
        if line_idx % 2 != 0:
            y_pts.reverse()
            
        for y in y_pts:
            max_hit_z = -1e9
            hit = False
            best_nx, best_ny, best_nz = 0, 0, 0
            
            # Non-recursive intersect
            stack = [0]
            while stack:
                node_idx = stack.pop()
                node = bvh[node_idx]
                
                if x >= node.min_x and x <= node.max_x and y >= node.min_y and y <= node.max_y:
                    if node.count > 0:
                        for i in range(node.first, node.first + node.count):
                            tri = triangles[tri_indices[i]]
                            is_hit, t = ray_triangle_intersect(x, y, z_start, tri[0], tri[1], tri[2], tri[3], tri[4], tri[5], tri[6], tri[7], tri[8])
                            if is_hit:
                                hit_z = z_start - t
                                if hit_z > max_hit_z:
                                    max_hit_z = hit_z
                                    best_nx, best_ny, best_nz = tri[9], tri[10], tri[11]
                                    hit = True
                    else:
                        stack.append(node.right)
                        stack.append(node.left)
                        
            if hit:
                path.append((x, y, max_hit_z, best_nx, best_ny, best_nz))
        
        line_idx += 1
        x += line_width
        
    if not path:
        return {"error": "No path generated"}
        
    # Generate GCode
    gcode = []
    gcode.append("; Open5x Conformal Slicer Output (Python Engine)")
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
        px, py, pz, nx, ny, nz = pt
        points_json.append({"x": round(px, 2), "y": round(py, 2), "z": round(pz, 2)})
        
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
