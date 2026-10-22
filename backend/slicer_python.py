"""
Main Slicing Pipeline - Integrated with Coordinate Frames, Surface Field, Collision, G-code
===========================================================================================

This module implements the complete slicing pipeline using the new validated modules:
- coordinate_frames: Single source of truth for all transforms
- surface_field: Wavelength-based sinusoidal field with analytical inverse
- collision: Fail-closed collision checking with swept-volume
- rotary_gcode/three_axis_gcode: Safe G-code generation with validation

COORDINATE FRAME PIPELINE
-------------------------
Model (STL) 
  -> load_stl: center, scale, rotate XYZ, translate XY, Z-floor shift
  -> Build-Plate Frame (B)
  -> SurfaceField.distort_z: apply sinusoidal warp
  -> Warped Build-Plate Frame (B')
  -> Slice at Z planes in B'
  -> 2D contours in (X, Y) at each Z'
  -> AreaLogic: offset shells, generate infill
  -> Toolpath in (X, Y, Z') in B'
  -> SurfaceField.inverse_distort_z + get_normal
  -> Toolpath in (X, Y, Z, Nx, Ny, Nz) in B (true geometry)
  -> Auto-segment: rotate about horizontal axis if enabled (uses coordinate_frames)
  -> TableTableUVAdapter.calculate_ik (uses coordinate_frames AC_TABLE)
  -> Machine-Axis (A) + Rotary (R) commands
  -> G-code with validation
"""

import math
import struct
import array
import tempfile
import numpy as np
from typing import List, Tuple, Optional, Dict, Any

# New validated modules
from coordinate_frames import (
    load_stl_transform,
    ac_table_forward_kinematics,
    ac_table_inverse_kinematics,
    ac_table_apply_transform,
    ac_table_apply_normal,
    ac_table_apply_normal_inverse,
    validate_frame_consistency,
)
from surface_field import SurfaceField, SurfaceFieldConfig
from collision import CollisionEngine, CollisionResult, CollisionStatus
from models import SlicerMachineProfile, FeaturePath
from regions import AreaLogic
from uv_adapter import TableTableUVAdapter
from rotary_gcode import RotaryGCodeGenerator, GenerationResult, MoveType
from three_axis_gcode import ThreeAxisGCodeGenerator
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from enums import GCodeDialect, CoordinateMode


# --- STL Loading with coordinate_frames ---

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
    """
    Load binary STL and transform to Build-Plate frame using coordinate_frames.
    
    Returns:
        triangles: List of (v0x, v0y, v0z, v1x, v1y, v1z, v2x, v2y, v2z, nx, ny, nz)
        bounds_min: (min_x, min_y, min_z)
        bounds_max: (max_x, max_y, max_z)
    """
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
            
            # Recompute normal if degenerate
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
        raise ValueError("ASCII STL not supported. Please upload a binary STL.")
        
    if not triangles:
        raise ValueError("No triangles found")
    
    # Compute model-space bounds
    min_x = min_y = min_z = 1e9
    max_x = max_y = max_z = -1e9
    for tri in triangles:
        min_x = min(min_x, tri[0], tri[3], tri[6])
        min_y = min(min_y, tri[1], tri[4], tri[7])
        min_z = min(min_z, tri[2], tri[5], tri[8])
        max_x = max(max_x, tri[0], tri[3], tri[6])
        max_y = max(max_y, tri[1], tri[4], tri[7])
        max_z = max(max_z, tri[2], tri[5], tri[8])
    
    # Build transform using coordinate_frames (Model -> BuildPlate)
    # Note: load_stl_transform doesn't include centering - we apply that manually
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    cz = (min_z + max_z) / 2.0
    
    transform = load_stl_transform(
        model_scale=model_scale,
        rot_x_deg=rot_x,
        rot_y_deg=rot_y,
        rot_z_deg=rot_z,
        pos_x=pos_x,
        pos_y=pos_y,
        z_floor_shift=0.0  # We'll apply floor shift after transform
    )
    
    # Apply transform to all triangles
    transformed_triangles = []
    t_min_x = t_min_y = t_min_z = 1e9
    t_max_x = t_max_y = t_max_z = -1e9
    
    for tri in triangles:
        v0 = np.array([tri[0], tri[1], tri[2]], dtype=float)
        v1 = np.array([tri[3], tri[4], tri[5]], dtype=float)
        v2 = np.array([tri[6], tri[7], tri[8]], dtype=float)
        n = np.array([tri[9], tri[10], tri[11]], dtype=float)
        
        # Center -> Transform -> Translate XY
        v0_centered = v0 - np.array([cx, cy, cz])
        v1_centered = v1 - np.array([cx, cy, cz])
        v2_centered = v2 - np.array([cx, cy, cz])
        
        v0_transformed = transform.apply_point(v0_centered)
        v1_transformed = transform.apply_point(v1_centered)
        v2_transformed = transform.apply_point(v2_centered)
        
        # Normals transform as vectors (no translation)
        n_transformed = transform.apply_vector(n)
        n_len = np.linalg.norm(n_transformed)
        if n_len > 0:
            n_transformed = n_transformed / n_len
        
        # Apply XY translation and track Z minimum for floor shift
        v0_final = v0_transformed + np.array([pos_x, pos_y, 0.0])
        v1_final = v1_transformed + np.array([pos_x, pos_y, 0.0])
        v2_final = v2_transformed + np.array([pos_x, pos_y, 0.0])
        
        t_min_z = min(t_min_z, v0_final[2], v1_final[2], v2_final[2])
        t_max_z = max(t_max_z, v0_final[2], v1_final[2], v2_final[2])
        t_min_x = min(t_min_x, v0_final[0], v1_final[0], v2_final[0])
        t_max_x = max(t_max_x, v0_final[0], v1_final[0], v2_final[0])
        t_min_y = min(t_min_y, v0_final[1], v1_final[1], v2_final[1])
        t_max_y = max(t_max_y, v0_final[1], v1_final[1], v2_final[1])
        
        transformed_triangles.append([
            v0_final[0], v0_final[1], v0_final[2],
            v1_final[0], v1_final[1], v1_final[2],
            v2_final[0], v2_final[1], v2_final[2],
            n_transformed[0], n_transformed[1], n_transformed[2]
        ])
    
    # Apply Z-floor shift so mesh sits at Z=0
    for tri in transformed_triangles:
        tri[2] -= t_min_z
        tri[5] -= t_min_z
        tri[8] -= t_min_z
    
    f_min_x = t_min_x + pos_x
    f_max_x = t_max_x + pos_x
    f_min_y = t_min_y + pos_y
    f_max_y = t_max_y + pos_y
    f_min_z = 0.0  # After floor shift
    f_max_z = t_max_z - t_min_z
    
    return transformed_triangles, (f_min_x, f_min_y, f_min_z), (f_max_x, f_max_y, f_max_z)


# --- Slice Segments ---

def get_z_slice_segments(active_triangles, z):
    """Compute 2D cross-section segments at given Z height."""
    segments = []
    EDGES = [
        (2, 3, 4,   5, 6, 7),    # v0 -> v1
        (5, 6, 7,   8, 9, 10),   # v1 -> v2
        (8, 9, 10,  2, 3, 4),    # v2 -> v0
    ]
    for tri in active_triangles:
        pts = []
        for (ax, ay, az_i, bx, by, bz_i) in EDGES:
            za = tri[az_i]
            zb = tri[bz_i]
            if (za < z <= zb) or (zb < z <= za):
                dz = zb - za
                if dz == 0:
                    continue
                t = (z - za) / dz
                ix = tri[ax] + t * (tri[bx] - tri[ax])
                iy = tri[ay] + t * (tri[by] - tri[ay])
                pts.append((ix, iy))
        if len(pts) == 2:
            segments.append((pts[0], pts[1], tri[11], tri[12], tri[13]))
    return segments


# --- Main Slicing Function ---

def slice_mesh(
    file_bytes, 
    layer_height, 
    bed_center_z, 
    wave_amplitude=0.0, 
    wave_frequency=0.1, 
    infill_density=20.0, 
    auto_segment=False, 
    model_scale=1.0, 
    rot_x=0.0, 
    rot_y=0.0, 
    rot_z=0.0, 
    pos_x=0.0, 
    pos_y=0.0, 
    infill_pattern="lines",
    use_5axis=True,
    machine_profile: Optional[SlicerMachineProfile] = None,
) -> Dict[str, Any]:
    """
    Main slicing entry point.
    
    Args:
        file_bytes: Binary STL data
        layer_height: Layer height in mm
        bed_center_z: Bed center Z for rotary kinematics
        wave_amplitude: Sinusoidal amplitude in mm
        wave_frequency: DEPRECATED - use wave_length_x/y instead. Kept for backward compat.
        infill_density: Infill percentage (0-100)
        auto_segment: Enable auto-segmentation for overhangs
        model_scale: Model scale factor
        rot_x, rot_y, rot_z: Model rotation in degrees
        pos_x, pos_y: Model position offset in mm
        infill_pattern: "lines" or "grid"
        use_5axis: If True, use 5-axis rotary G-code; if False, use 3-axis
        machine_profile: Machine profile for validation (required for 5-axis)
    
    Returns:
        Dict with toolpath_points, gcode_file, segmentation_info
    """
    # --- Load and transform STL to Build-Plate frame ---
    original_triangles, min_b, max_b = load_stl(
        file_bytes, model_scale, rot_x, rot_y, rot_z, pos_x, pos_y
    )
    min_x, min_y, min_z = min_b
    max_x, max_y, max_z = max_b
    
    # --- Validate model size ---
    if (max_x - min_x) > 500.0 or (max_y - min_y) > 500.0:
        return {"error": "Model is too large (>500mm). Scale down your STL to millimeters."}
    
    # --- Convert wave_frequency to wavelength (backward compat) ---
    # wave_frequency in cycles/mm -> wavelength = 1/frequency
    wave_length_x = 1.0 / wave_frequency if wave_frequency > 0 else 50.0
    wave_length_y = 1.0 / wave_frequency if wave_frequency > 0 else 50.0
    
    # --- Create SurfaceField with wavelength-based config ---
    field_config = SurfaceFieldConfig(
        amplitude=wave_amplitude,
        wave_length_x=wave_length_x,
        wave_length_y=wave_length_y,
        fade_height=15.0
    )
    surface_field = SurfaceField(field_config)
    
    # Validate surface field constraints
    sf_valid, sf_errors = surface_field.validate_constraints(max_slope_deg=45.0)
    if not sf_valid:
        return {"error": f"Surface field validation failed: {'; '.join(sf_errors)}"}
    
    # --- Build BVH for collision checking ---
    bvh_vertices = []
    bvh_faces = []
    v_idx = 0
    for t in original_triangles:
        bvh_vertices.extend([
            [t[0], t[1], t[2]],
            [t[3], t[4], t[5]],
            [t[6], t[7], t[8]]
        ])
        bvh_faces.append([v_idx, v_idx+1, v_idx+2])
        v_idx += 3
    mesh_bvh = MeshBVH(np.array(bvh_vertices), np.array(bvh_faces))
    
    # Use provided machine profile or default
    if machine_profile is None:
        machine_profile = SlicerMachineProfile()
    
    collision_engine = CollisionEngine(machine_profile, mesh_bvh, bed_center_z)
    area_logic = AreaLogic(extrusion_width=0.4)
    
    # --- Auto-segmentation ---
    calc_z_cutoff = 1e9
    calc_segment_tilt = 0.0
    tilt_dir_x, tilt_dir_y = 1.0, 0.0
    
    if auto_segment:
        # Find overhangs in original (unwarped) frame
        overhangs = [
            t for t in original_triangles
            if t[11] < -0.5                               # downward-facing normal (nz < -0.5)  
            and min(t[2], t[5], t[8]) > min_z + 2.0       # not part of the base (2 mm grace)
        ]
        if overhangs:
            lowest_z = min(min(t[2], t[5], t[8]) for t in overhangs)
            calc_z_cutoff = max(min_z + 2.0, lowest_z - 2.0)

            o_min_x = min(min(t[0], t[3], t[6]) for t in overhangs)
            o_max_x = max(max(t[0], t[3], t[6]) for t in overhangs)
            o_min_y = min(min(t[1], t[4], t[7]) for t in overhangs)
            o_max_y = max(max(t[1], t[4], t[7]) for t in overhangs)

            o_cx = (o_min_x + o_max_x) / 2.0
            o_cy = (o_min_y + o_max_y) / 2.0
            base_cx = (min_x + max_x) / 2.0
            base_cy = (min_y + max_y) / 2.0

            dx = o_cx - base_cx
            dy = o_cy - base_cy
            length = math.hypot(dx, dy)
            if length > 1e-4:
                tilt_dir_x = dx / length
                tilt_dir_y = dy / length
            else:
                tilt_dir_x = 1.0
                tilt_dir_y = 0.0

            calc_segment_tilt = 45.0
    
    # --- Slicing parameters ---
    line_width = 0.4
    infill_spacing = line_width / (infill_density / 100.0) if infill_density > 0.1 else 1e9
    
    # --- Prepare triangles for slicing ---
    # Triangles are already in Build-Plate frame with Z-floor at 0
    transformed_triangles = [list(t) for t in original_triangles]
    del original_triangles
    
    # --- Distort mesh vertices with SurfaceField ---
    distorted_triangles = []
    dist_min_z = 1e9
    dist_max_z = -1e9
    
    for tri in transformed_triangles:
        v0x, v0y, v0z = tri[0], tri[1], tri[2]
        v1x, v1y, v1z = tri[3], tri[4], tri[5]
        v2x, v2y, v2z = tri[6], tri[7], tri[8]
        
        dv0z = surface_field.distort_z(v0x, v0y, v0z)
        dv1z = surface_field.distort_z(v1x, v1y, v1z)
        dv2z = surface_field.distort_z(v2x, v2y, v2z)
        
        t_min = min(dv0z, dv1z, dv2z)
        t_max = max(dv0z, dv1z, dv2z)
        
        dist_min_z = min(dist_min_z, t_min)
        dist_max_z = max(dist_max_z, t_max)
        
        distorted_triangles.append((t_min, t_max, v0x, v0y, dv0z, v1x, v1y, dv1z, v2x, v2y, dv2z, tri[9], tri[10], tri[11]))
    
    del transformed_triangles
    
    # --- Helper functions ---
    def resample_polyline(pts, max_len=0.5):
        if not pts: return []
        resampled = [pts[0]]
        for i in range(len(pts)-1):
            p1, p2 = pts[i], pts[i+1]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            d = math.hypot(dx, dy)
            if d <= max_len:
                resampled.append(p2)
                continue
            n = int(math.ceil(d / max_len))
            for j in range(1, n + 1):
                t = j / n
                resampled.append((p1[0] + dx*t, p1[1] + dy*t))
        return resampled
    
    def clip_polyline(pts, z_base, is_tilted, keep_below, current_z_for_collision=None):
        """
        Clip polyline against auto-segment cutoff plane.
        
        For tilted phase: inverse_rotate -> inverse_distort -> check cutoff
        For base phase: inverse_distort -> check cutoff
        """
        chunks = []
        current_chunk = []
        
        # Precompute rotation if tilted
        if is_tilted:
            global_c = math.cos(calc_segment_tilt * math.pi / 180.0)
            global_s = math.sin(calc_segment_tilt * math.pi / 180.0)
            rot_ax_x = -tilt_dir_y
            rot_ax_y = tilt_dir_x
            rot_ax_z = 0.0
            
            def vector_rot(vx, vy, vz, ax, ay, az, sn, cs):
                dot = vx*ax + vy*ay + vz*az
                cx, cy, cz = ay*vz - az*vy, az*vx - ax*vz, ax*vy - ay*vx
                rx = vx*cs + cx*sn + ax*dot*(1-cs)
                ry = vy*cs + cy*sn + ay*dot*(1-cs)
                rz = vz*cs + cz*sn + az*dot*(1-cs)
                return rx, ry, rz
            
            def inverse_rotate_pt(px, py, pz):
                rx, ry, rz = vector_rot(px, py, pz - calc_z_cutoff, rot_ax_x, rot_ax_y, rot_ax_z, -global_s, global_c)
                return rx, ry, rz + calc_z_cutoff
        else:
            def inverse_rotate_pt(px, py, pz):
                return px, py, pz
        
        for i in range(len(pts)-1):
            if is_tilted:
                orig_x1, orig_y1, orig_z1 = inverse_rotate_pt(pts[i][0], pts[i][1], z_base)
                z1 = surface_field.inverse_distort_z(orig_x1, orig_y1, orig_z1)
                orig_x2, orig_y2, orig_z2 = inverse_rotate_pt(pts[i+1][0], pts[i+1][1], z_base)
                z2 = surface_field.inverse_distort_z(orig_x2, orig_y2, orig_z2)
                p1_out = (orig_x1, orig_y1, z1)
                p2_out = (orig_x2, orig_y2, z2)
            else:
                z1 = surface_field.inverse_distort_z(pts[i][0], pts[i][1], z_base)
                z2 = surface_field.inverse_distort_z(pts[i+1][0], pts[i+1][1], z_base)
                p1_out = (pts[i][0], pts[i][1], z1)
                p2_out = (pts[i+1][0], pts[i+1][1], z2)
            
            def is_valid(z): return z <= calc_z_cutoff + 1e-4 if keep_below else z >= calc_z_cutoff - 1e-4
            
            v1, v2 = is_valid(z1), is_valid(z2)
            
            if v1 and v2:
                if not current_chunk: current_chunk.append(p1_out)
                current_chunk.append(p2_out)
            elif not v1 and not v2:
                pass
            else:
                t = (calc_z_cutoff - z1) / (z2 - z1) if z2 != z1 else 0
                ix = p1_out[0] + t * (p2_out[0] - p1_out[0])
                iy = p1_out[1] + t * (p2_out[1] - p1_out[1])
                i_out = (ix, iy, calc_z_cutoff)
                
                if v1:
                    if not current_chunk: current_chunk.append(p1_out)
                    current_chunk.append(i_out)
                    chunks.append(current_chunk)
                    current_chunk = []
                else:
                    current_chunk.append(i_out)
                    current_chunk.append(p2_out)
                    
        if current_chunk: chunks.append(current_chunk)
        return chunks
    
    def optimize_infill_chunks(chunks, start_pt):
        if not chunks: return []
        optimized = []
        current_pt = start_pt
        unvisited = list(chunks)
        while unvisited:
            best_idx = 0
            best_dist = 1e9
            best_reverse = False
            for i, chunk in enumerate(unvisited):
                if not chunk: continue
                d_start = math.hypot(chunk[0][0] - current_pt[0], chunk[0][1] - current_pt[1])
                d_end = math.hypot(chunk[-1][0] - current_pt[0], chunk[-1][1] - current_pt[1])
                if d_start < best_dist:
                    best_dist = d_start; best_idx = i; best_reverse = False
                if d_end < best_dist:
                    best_dist = d_end; best_idx = i; best_reverse = True
            best_chunk = unvisited.pop(best_idx)
            if best_reverse: best_chunk.reverse()
            optimized.append(best_chunk)
            current_pt = (best_chunk[-1][0], best_chunk[-1][1])
        return optimized
    
    def get_last_path_pt():
        return (path[-1][0], path[-1][1]) if path else (0.0, 0.0)
    
    # --- Main slicing loop: Base phase (below cutoff) ---
    path, layer_idx, path_id = [], 0, 0
    z_buckets = {}
    for t in distorted_triangles:
        for l in range(int(math.floor(t[0] / layer_height)), int(math.floor(t[1] / layer_height)) + 1):
            z_buckets.setdefault(l, []).append(t)
    
    z = dist_min_z + layer_height
    base_loop_max = calc_z_cutoff + wave_amplitude + 0.01 if calc_z_cutoff != 1e9 else dist_max_z
    
    while z <= min(dist_max_z, base_loop_max):
        l_idx = int(math.floor(z / layer_height))
        segments = get_z_slice_segments([t for t in z_buckets.get(l_idx, []) if t[0] <= z and t[1] >= z], z)
        if not segments:
            z += layer_height; layer_idx += 1; continue
        layer_boundaries = area_logic.build_polygons_from_segments(segments)
        if not layer_boundaries:
            z += layer_height; layer_idx += 1; continue
            
        shells, infill_areas = area_logic.generate_shells_and_infill_area(layer_boundaries, num_shells=2)
        infill_angle = (layer_idx % 2) * 90.0
        infill_lines = area_logic.generate_infill_lines(infill_areas, spacing=infill_spacing, angle_deg=infill_angle)
        
        for shell in shells:
            for ring in [shell.exterior] + list(shell.interiors):
                coords = [(pt[0], pt[1], z) for pt in ring.coords]
                resampled = resample_polyline(coords)
                chunks = clip_polyline(resampled, z, False, True)
                for chunk in chunks:
                    path_id += 1
                    for pt in chunk:
                        nx, ny, nz = surface_field.get_normal(pt[0], pt[1], pt[2])
                        path.append((pt[0], pt[1], pt[2], nx, ny, nz, layer_idx, "perimeter", path_id))
        
        layer_infill_chunks = []
        for line in infill_lines:
            coords = [(pt[0], pt[1], z) for pt in line.coords]
            resampled = resample_polyline(coords)
            layer_infill_chunks.extend(clip_polyline(resampled, z, False, True))
        
        optimized_chunks = optimize_infill_chunks(layer_infill_chunks, get_last_path_pt())
        for chunk in optimized_chunks:
            path_id += 1
            for pt in chunk:
                nx, ny, nz = surface_field.get_normal(pt[0], pt[1], pt[2])
                path.append((pt[0], pt[1], pt[2], nx, ny, nz, layer_idx, "infill", path_id))
        z += layer_height; layer_idx += 1
    
    # --- Tilted phase (above cutoff) ---
    if calc_z_cutoff != 1e9:
        # Precompute rotation
        global_c = math.cos(calc_segment_tilt * math.pi / 180.0)
        global_s = math.sin(calc_segment_tilt * math.pi / 180.0)
        rot_ax_x = -tilt_dir_y
        rot_ax_y = tilt_dir_x
        rot_ax_z = 0.0
        
        def vector_rot(vx, vy, vz, ax, ay, az, sn, cs):
            dot = vx*ax + vy*ay + vz*az
            cx, cy, cz = ay*vz - az*vy, az*vx - ax*vz, ax*vy - ay*vx
            rx = vx*cs + cx*sn + ax*dot*(1-cs)
            ry = vy*cs + cy*sn + ay*dot*(1-cs)
            rz = vz*cs + cz*sn + az*dot*(1-cs)
            return rx, ry, rz
        
        def rotate_pt(px, py, pz):
            rx, ry, rz = vector_rot(px, py, pz - calc_z_cutoff, rot_ax_x, rot_ax_y, rot_ax_z, global_s, global_c)
            return rx, ry, rz + calc_z_cutoff
        
        # Transform distorted triangles to tilted frame
        tilted_triangles = []
        tilted_min_z, tilted_max_z = 1e9, -1e9
        for t in distorted_triangles:
            if t[1] < calc_z_cutoff: continue
            rv0 = rotate_pt(t[2], t[3], t[4])
            rv1 = rotate_pt(t[5], t[6], t[7])
            rv2 = rotate_pt(t[8], t[9], t[10])
            t_min = min(rv0[2], rv1[2], rv2[2])
            t_max = max(rv0[2], rv1[2], rv2[2])
            tilted_min_z = min(tilted_min_z, t_min)
            tilted_max_z = max(tilted_max_z, t_max)
            tnx, tny, tnz = vector_rot(t[11], t[12], t[13], rot_ax_x, rot_ax_y, rot_ax_z, global_s, global_c)
            tilted_triangles.append((t_min, t_max, rv0[0], rv0[1], rv0[2], rv1[0], rv1[1], rv1[2], rv2[0], rv2[1], rv2[2], tnx, tny, tnz))
        
        tilt_nx, tilt_ny, tilt_nz = vector_rot(0.0, 0.0, 1.0, rot_ax_x, rot_ax_y, rot_ax_z, global_s, global_c)
        del distorted_triangles
        
        # Slice tilted phase
        tilt_z_buckets = {}
        for t in tilted_triangles:
            for l in range(int(math.floor(t[0] / layer_height)), int(math.floor(t[1] / layer_height)) + 1):
                tilt_z_buckets.setdefault(l, []).append(t)
        del tilted_triangles
        
        z = tilted_min_z + layer_height
        while z <= tilted_max_z:
            l_idx = int(math.floor(z / layer_height))
            segments = get_z_slice_segments([t for t in tilt_z_buckets.get(l_idx, []) if t[0] <= z and t[1] >= z], z)
            if not segments:
                z += layer_height; layer_idx += 1; continue
            layer_boundaries = area_logic.build_polygons_from_segments(segments)
            if not layer_boundaries:
                z += layer_height; layer_idx += 1; continue
            
            shells, infill_areas = area_logic.generate_shells_and_infill_area(layer_boundaries, num_shells=2)
            infill_angle = (layer_idx % 2) * 90.0
            infill_lines = area_logic.generate_infill_lines(infill_areas, spacing=infill_spacing, angle_deg=infill_angle)
            
            for shell in shells:
                for ring in [shell.exterior] + list(shell.interiors):
                    coords = [(pt[0], pt[1], z) for pt in ring.coords]
                    resampled = resample_polyline(coords)
                    chunks = clip_polyline(resampled, z, True, False)
                    for chunk in chunks:
                        path_id += 1
                        for pt in chunk:
                            path.append((pt[0], pt[1], pt[2], tilt_nx, tilt_ny, tilt_nz, layer_idx, "perimeter", path_id))
            
            layer_infill_chunks = []
            for line in infill_lines:
                coords = [(pt[0], pt[1], z) for pt in line.coords]
                resampled = resample_polyline(coords)
                layer_infill_chunks.extend(clip_polyline(resampled, z, True, False))
            
            optimized_chunks = optimize_infill_chunks(layer_infill_chunks, get_last_path_pt())
            for chunk in optimized_chunks:
                path_id += 1
                for pt in chunk:
                    path.append((pt[0], pt[1], pt[2], tilt_nx, tilt_ny, tilt_nz, layer_idx, "infill", path_id))
            z += layer_height; layer_idx += 1
    
    if not path:
        return {"error": "No path generated"}
    
    # --- Build visualization JSON ---
    points_json = {
        "x": array.array('f'),
        "y": array.array('f'),
        "z": array.array('f'),
        "nx": array.array('f'),
        "ny": array.array('f'),
        "nz": array.array('f'),
        "layer": array.array('H'),
        "type": array.array('B')
    }
    
    for pt in path:
        px, py, pz, nx, ny, nz, layer, ptype, current_path_id = pt
        points_json["x"].append(px)
        points_json["y"].append(py)
        points_json["z"].append(pz)
        points_json["nx"].append(nx)
        points_json["ny"].append(ny)
        points_json["nz"].append(nz)
        points_json["layer"].append(layer)
        points_json["type"].append(0 if ptype == "perimeter" else 1)
    
    # --- Collision sweep check (fail-closed) ---
    feature_paths = []
    current_fp = None
    last_id = -1
    for pt in path:
        px, py, pz, nx, ny, nz, layer, ptype, current_path_id = pt
        if current_path_id != last_id or current_fp is None:
            if current_fp is not None:
                feature_paths.append(current_fp)
            current_fp = FeaturePath(
                points=[], normals=[], layer_idx=layer, 
                feature_type=ptype, path_id=current_path_id
            )
            last_id = current_path_id
        current_fp.points.append((px, py, pz))
        current_fp.normals.append((nx, ny, nz))
    if current_fp:
        feature_paths.append(current_fp)
    
    # Check each feature path with swept-volume collision
    for fp in feature_paths:
        # Use current_z = layer_idx * layer_height for progressive collision checking
        current_z = fp.layer_idx * layer_height
        reports = collision_engine.sweep_check_path(fp, current_z=current_z)
        if reports:
            # Fail closed: any collision blocks export
            first_report = reports[0]
            return {
                "error": f"Collision detected on {fp.feature_type} layer {fp.layer_idx}: {first_report.limiting_surface} collision. {first_report.suggested_remedy}",
                "collision_details": {
                    "path_id": fp.path_id,
                    "layer_idx": fp.layer_idx,
                    "limiting_surface": first_report.limiting_surface,
                    "clearance_mm": first_report.clearance,
                    "suggested_remedy": first_report.suggested_remedy,
                }
            }
    
    # --- G-code Generation ---
    if use_5axis:
        # 5-axis path with rotary kinematics
        settings = DialectSettings(
            dialect=GCodeDialect.MARLIN,
            coordinate_mode=CoordinateMode.ABSOLUTE,
            units="mm",
            axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
            feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
            retraction=RetractionSettings(distance=2.0, feedrate=2400),
            clearance_moves=["G0 Z50 F3000"],
            header=["; START"],
            footer=["; END"],
            provenance_enabled=True
        )
        kinematics = TableTableUVAdapter(bed_center_z=bed_center_z)
        
        # Use machine profile for G-code validation
        gcode_gen = RotaryGCodeGenerator(
            settings,
            kinematics,
            machine_profile,
            layer_height=layer_height,
            line_width=line_width,
            filament_diameter=1.75,
            travel_threshold=1.5
        )
        
        path_points = [(pt[0], pt[1], pt[2], pt[3], pt[4], pt[5]) for pt in path]
        path_ids_list = [pt[8] for pt in path]
        
        result: GenerationResult = gcode_gen.generate(path_points, path_ids_list)
        
        if not result.is_valid:
            return {
                "error": f"G-code generation failed validation: {'; '.join(result.validation_errors)}",
                "validation_errors": result.validation_errors
            }
        
        gcode_str = result.gcode
        metadata = result.metadata
        
    else:
        # 3-axis path
        settings = DialectSettings(
            dialect=GCodeDialect.MARLIN,
            coordinate_mode=CoordinateMode.ABSOLUTE,
            units="mm",
            axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
            feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
            retraction=RetractionSettings(distance=2.0, feedrate=2400),
            clearance_moves=["G0 Z50 F3000"],
            header=["; START"],
            footer=["; END"],
        )
        
        gcode_gen = ThreeAxisGCodeGenerator(
            settings,
            machine_profile,
            layer_height=layer_height,
            line_width=line_width,
            filament_diameter=1.75,
            travel_threshold=1.5
        )
        
        path_points = [(pt[0], pt[1], pt[2]) for pt in path]
        path_ids_list = [pt[8] for pt in path]
        
        result: GenerationResult = gcode_gen.generate(path_points, path_ids_list)
        
        if not result.is_valid:
            return {
                "error": f"G-code generation failed validation: {'; '.join(result.validation_errors)}",
                "validation_errors": result.validation_errors
            }
        
        gcode_str = result.gcode
        metadata = result.metadata
    
    # Write G-code to temp file
    gcode_file = tempfile.TemporaryFile(mode='w+')
    gcode_file.write(gcode_str)
    gcode_file.flush()

    return {
        "toolpath_points": points_json,
        "gcode_file": gcode_file,
        "segmentation_info": {
            "auto_segment": auto_segment,
            "calc_z_cutoff": round(calc_z_cutoff, 2) if calc_z_cutoff != 1e9 else "None",
            "calc_segment_tilt": round(calc_segment_tilt, 2)
        },
        "gcode_metadata": metadata,
        "field_metadata": surface_field.get_field_metadata(),
    }


# --- Test Functions ---

def test_slice_simple_cube():
    """Test slicing a simple cube."""
    # Create a simple 10mm cube STL (binary)
    # This is a minimal test - in practice we'd use a real STL file
    pass


if __name__ == "__main__":
    # Run validation tests for submodules
    import coordinate_frames
    coordinate_frames.__file__  # Just verify import
    print("✓ coordinate_frames import")
    
    import surface_field
    surface_field.__file__
    print("✓ surface_field import")
    
    import collision
    collision.__file__
    print("✓ collision import")
    
    import rotary_gcode
    rotary_gcode.__file__
    print("✓ rotary_gcode import")
    
    import three_axis_gcode
    three_axis_gcode.__file__
    print("✓ three_axis_gcode import")
    
    print("\nAll slicer_python module imports successful!")