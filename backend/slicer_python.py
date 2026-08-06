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
                
def slice_mesh(file_bytes, layer_height, bed_center_z, wave_amplitude=0.0, wave_frequency=0.1, infill_density=20.0, auto_segment=False, model_scale=1.0, rot_x=0.0, rot_y=0.0, rot_z=0.0, pos_x=0.0, pos_y=0.0, infill_pattern="lines"):
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
        
    def distort_toolpath_z(x, y, z):
        wave = wave_amplitude * math.sin(wave_frequency * x) * math.cos(wave_frequency * y)
        return z + get_attenuation(z) * wave
        
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
    
    distorted_triangles = []
    min_x, min_y, min_z = min_b
    max_x, max_y, max_z = max_b
    
    dist_min_z = 1e9
    dist_max_z = -1e9
    
    for tri in subdivided_triangles:
        v0x, v0y, v0z = tri[0], tri[1], tri[2]
        v1x, v1y, v1z = tri[3], tri[4], tri[5]
        v2x, v2y, v2z = tri[6], tri[7], tri[8]
        
        dv0z = distort_mesh_z(v0x, v0y, v0z)
        dv1z = distort_mesh_z(v1x, v1y, v1z)
        dv2z = distort_mesh_z(v2x, v2y, v2z)
        
        t_min = min(dv0z, dv1z, dv2z)
        t_max = max(dv0z, dv1z, dv2z)
        
        dist_min_z = min(dist_min_z, t_min)
        dist_max_z = max(dist_max_z, t_max)
        
        distorted_triangles.append((t_min, t_max, v0x, v0y, dv0z, v1x, v1y, dv1z, v2x, v2y, dv2z, tri[9], tri[10], tri[11]))
    
    calc_z_cutoff = 1e9
    calc_segment_tilt = 0.0
    
    if auto_segment:
        # Ignore overhangs within 15mm of the bed (usually just base chamfers/fillets)
        overhangs = [t for t in original_triangles if t[11] < -0.5 and min(t[2], t[5], t[8]) > min_z + 15.0]
        if overhangs:
            lowest_z = min(min(t[2], t[5], t[8]) for t in overhangs)
            calc_z_cutoff = max(min_z + 2.0, lowest_z - 2.0)
            avg_ny = sum(t[10] for t in overhangs) / len(overhangs)
            calc_segment_tilt = -45.0 if avg_ny > 0 else 45.0
            
    if (max_x - min_x) > 500.0 or (max_y - min_y) > 500.0:
        return {"error": "Model is too large (>500mm). Scale down your STL to millimeters to prevent memory crash."}
        
    line_width = 0.4 # Default nozzle line width
    if infill_density <= 0.1:
        infill_spacing = 1e9 # effectively no infill
    else:
        infill_spacing = line_width / (infill_density / 100.0)
    
    path = []
    layer_idx = 0
    
    z_buckets = {}
    for t in distorted_triangles:
        min_l = int(math.floor(t[0] / layer_height))
        max_l = int(math.floor(t[1] / layer_height))
        for l in range(min_l, max_l + 1):
            if l not in z_buckets: z_buckets[l] = []
            z_buckets[l].append(t)
    
    z = dist_min_z + layer_height
    base_loop_max = calc_z_cutoff + wave_amplitude + 0.01 if calc_z_cutoff != 1e9 else dist_max_z
    while z <= min(dist_max_z, base_loop_max):
        l_idx = int(math.floor(z / layer_height))
        bucket_tris = z_buckets.get(l_idx, [])
        active_triangles = [t for t in bucket_tris if t[0] <= z and t[1] >= z]
        segments = get_z_slice_segments(active_triangles, z)
        if not segments:
            z += layer_height
            layer_idx += 1
            continue
            
        # 1. Perimeters (5-axis tilted)
        loops = chain_segments(segments)
        for loop in loops:
            for seg in loop:
                resampled = resample_pts(seg[0], seg[1])
                for pt in resampled[:-1]:
                    true_z = distort_toolpath_z(pt[0], pt[1], z)
                    if true_z > calc_z_cutoff: continue
                    nx, ny, nz = get_wavy_normal(pt[0], pt[1], true_z)
                    path.append((pt[0], pt[1], true_z, nx, ny, nz, layer_idx, "perimeter"))
            if loop:
                last_pt = loop[-1][1]
                true_z = distort_toolpath_z(last_pt[0], last_pt[1], z)
                if true_z <= calc_z_cutoff:
                    nx, ny, nz = get_wavy_normal(last_pt[0], last_pt[1], true_z)
                    path.append((last_pt[0], last_pt[1], true_z, nx, ny, nz, layer_idx, "perimeter"))
                
        # 2. Infill (Straight down or wavy)
        infill_pts = generate_infill(segments, min_x, max_x, min_y, max_y, infill_spacing, infill_pattern, layer_idx)
        for i in range(0, len(infill_pts), 2):
            p1, p2 = infill_pts[i], infill_pts[i+1]
            resampled = resample_pts(p1, p2)
            for pt in resampled:
                true_z = distort_toolpath_z(pt[0], pt[1], z)
                if true_z > calc_z_cutoff: continue
                nx, ny, nz = get_wavy_normal(pt[0], pt[1], true_z)
                path.append((pt[0], pt[1], true_z, nx, ny, nz, layer_idx, "infill"))
            
        z += layer_height
        layer_idx += 1
        
    # 2. Overhang Segment Loop (Support-Free Tilted Slicing)
    if max_z > calc_z_cutoff and calc_segment_tilt != 0.0:
        tilt_rad = calc_segment_tilt * math.pi / 180.0
        c = math.cos(tilt_rad)
        s = math.sin(tilt_rad)
        cz = calc_z_cutoff
        
        tilted_triangles = []
        tilted_min_z = 1e9
        tilted_max_z = -1e9
        tilted_min_x = 1e9
        tilted_max_x = -1e9
        tilted_min_y = 1e9
        tilted_max_y = -1e9
        
        def rotate_pt(px, py, pz):
            dy = py
            dz = pz - cz
            ny = dy * c - dz * s
            nz = dy * s + dz * c
            return px, ny, nz + cz
            
        def inverse_rotate_pt(px, py, pz):
            dy = py
            dz = pz - cz
            ny = dy * c + dz * s
            nz = -dy * s + dz * c
            return px, ny, nz + cz
            
        for t in distorted_triangles:
            if t[1] < calc_z_cutoff: continue # Skip triangles completely below cutoff
            
            rv0 = rotate_pt(t[2], t[3], t[4])
            rv1 = rotate_pt(t[5], t[6], t[7])
            rv2 = rotate_pt(t[8], t[9], t[10])
            
            t_min = min(rv0[2], rv1[2], rv2[2])
            t_max = max(rv0[2], rv1[2], rv2[2])
            tilted_min_z = min(tilted_min_z, t_min)
            tilted_max_z = max(tilted_max_z, t_max)
            
            tilted_min_x = min(tilted_min_x, rv0[0], rv1[0], rv2[0])
            tilted_max_x = max(tilted_max_x, rv0[0], rv1[0], rv2[0])
            tilted_min_y = min(tilted_min_y, rv0[1], rv1[1], rv2[1])
            tilted_max_y = max(tilted_max_y, rv0[1], rv1[1], rv2[1])
            
            # Rotate normal
            rnx = t[11]
            rny = t[12] * c - t[13] * s
            rnz = t[12] * s + t[13] * c
            tilted_triangles.append((t_min, t_max, rv0[0], rv0[1], rv0[2], rv1[0], rv1[1], rv1[2], rv2[0], rv2[1], rv2[2], rnx, rny, rnz))
            
        tilt_nx = 0.0
        tilt_ny = s
        tilt_nz = c
        
        tilt_z_buckets = {}
        for t in tilted_triangles:
            min_l = int(math.floor(t[0] / layer_height))
            max_l = int(math.floor(t[1] / layer_height))
            for l in range(min_l, max_l + 1):
                if l not in tilt_z_buckets: tilt_z_buckets[l] = []
                tilt_z_buckets[l].append(t)
        
        z = tilted_min_z + layer_height
        while z <= tilted_max_z:
            l_idx = int(math.floor(z / layer_height))
            bucket_tris = tilt_z_buckets.get(l_idx, [])
            active_triangles = [t for t in bucket_tris if t[0] <= z and t[1] >= z]
            segments = get_z_slice_segments(active_triangles, z)
            if not segments:
                z += layer_height
                layer_idx += 1
                continue
                
            loops = chain_segments(segments)
            for loop in loops:
                for seg in loop:
                    resampled = resample_pts(seg[0], seg[1])
                    for pt in resampled[:-1]:
                        orig_x, orig_y, orig_z = inverse_rotate_pt(pt[0], pt[1], z)
                        true_z = distort_toolpath_z(orig_x, orig_y, orig_z)
                        if true_z < calc_z_cutoff: continue
                        path.append((orig_x, orig_y, true_z, tilt_nx, tilt_ny, tilt_nz, layer_idx, "perimeter"))
                if loop:
                    last_pt = loop[-1][1]
                    orig_x, orig_y, orig_z = inverse_rotate_pt(last_pt[0], last_pt[1], z)
                    true_z = distort_toolpath_z(orig_x, orig_y, orig_z)
                    if true_z >= calc_z_cutoff:
                        path.append((orig_x, orig_y, true_z, tilt_nx, tilt_ny, tilt_nz, layer_idx, "perimeter"))
                    
            infill_pts = generate_infill(segments, tilted_min_x, tilted_max_x, tilted_min_y, tilted_max_y, infill_spacing, infill_pattern, layer_idx)
            for i in range(0, len(infill_pts), 2):
                p1, p2 = infill_pts[i], infill_pts[i+1]
                resampled = resample_pts(p1, p2)
                for pt in resampled:
                    orig_x, orig_y, orig_z = inverse_rotate_pt(pt[0], pt[1], z)
                    true_z = distort_toolpath_z(orig_x, orig_y, orig_z)
                    if true_z < calc_z_cutoff: continue
                    path.append((orig_x, orig_y, true_z, tilt_nx, tilt_ny, tilt_nz, layer_idx, "infill"))
                
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
    
    points_json = {
        "x": [],
        "y": [],
        "z": [],
        "layer": [],
        "type": []
    }
    
    for pt in path:
        px, py, pz, nx, ny, nz, layer, ptype = pt
        points_json["x"].append(round(px, 2))
        points_json["y"].append(round(py, 2))
        points_json["z"].append(round(pz, 2))
        points_json["layer"].append(layer)
        points_json["type"].append(0 if ptype == "perimeter" else 1)
        
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
        
        # If moving to a new layer, jumping across infill, or jumping across cutoff gaps, retract and move
        if dist_part > 1.5:
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
        "gcode": "\\n".join(gcode) + "\\n",
        "segmentation_info": {
            "auto_segment": auto_segment,
            "calc_z_cutoff": round(calc_z_cutoff, 2) if calc_z_cutoff != 1e9 else "None",
            "calc_segment_tilt": round(calc_segment_tilt, 2)
        }
    }
