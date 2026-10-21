import io
import trimesh
from typing import Dict, Any, Tuple, Callable
from enums import JobMode, JobStage, DiagnosticStatus, DiagnosticSeverity
from validation_model import ValidationDiagnostic, ValidationResult
from progress_model import StageProgressEvent

import transform_utils
import slicer_python

from chunk_builder import build_capped_chunks, subtract_later_chunks
from chunk_slicer import slice_chunk
from plane_preflight import preflight_slice_plane
from polygonization import reconstruct_polygons
from slice_intersection import slice_mesh_at_z
from layer_schedule import generate_layer_schedule
from transform_utils import align_chunk_to_slice_plane
from collision import CollisionEngine
from bvh import MeshBVH
from models import SlicerMachineProfile
from regions import AreaLogic
from slice_plane_model import SlicePlane
from rotary_gcode import RotaryGCodeGenerator
from uv_adapter import TableTableUVAdapter
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from enums import GCodeDialect, CoordinateMode
from shapely.geometry import LineString, Polygon, MultiPolygon
import numpy as np

from infill_generator import generate_line_infill
from path_ordering import order_paths

class JobCancelledError(Exception):
    """Raised when a job is cooperatively cancelled during execution."""
    pass


def _check_chunk_ge_1_collision(
    collision_engine: CollisionEngine,
    pts_world: np.ndarray,
    norms_world: np.ndarray,
    local_mesh: trimesh.Trimesh,
    mat: np.ndarray,
    z: float,
    profile: SlicerMachineProfile,
    cached_bvh: MeshBVH | None,
) -> np.ndarray:
    """Check collision for chunk index >= 1 against printed material.

    Printed material = all earlier chunks (cached BVH, world frame) UNION
    the current chunk's already-printed part (clip by current layer, mapped
    to world frame). Returns a bool array of per-point collision flags.
    """
    holder_ends = pts_world + norms_world * profile.nozzle_length
    collisions = np.zeros(len(pts_world), dtype=bool)
    holder_radius = profile.nozzle_holder_radius

    # --- Bbox early-out for earlier chunks ---
    # If holder_end is far from earlier chunks' bbox, skip the query.
    if cached_bvh is not None:
        earlier_mesh = cached_bvh.get_mesh()
        earlier_bbox_min = earlier_mesh.bounds[0]
        earlier_bbox_max = earlier_mesh.bounds[1]
        # Expand bbox by holder_radius for conservative check
        expanded_min = earlier_bbox_min - holder_radius
        expanded_max = earlier_bbox_max + holder_radius
        # Check which holder_ends are outside the expanded bbox
        outside_bbox = np.any(holder_ends < expanded_min, axis=1) | np.any(holder_ends > expanded_max, axis=1)
        inside_idx = np.nonzero(~outside_bbox)[0]
        if len(inside_idx) > 0:
            collisions[inside_idx] = collision_engine.batch_check_poses_with_bvh(
                pts_world[inside_idx], norms_world[inside_idx], cached_bvh
            )
        # Points outside bbox remain False (no collision with earlier chunks)

    # Also check current chunk's already-printed part (clip below this layer).
    # Uses manifold3d trim_by_plane for a capped clip, mapped to world frame,
    # then checked via batch_check_poses_with_bvh.
    clip_result = collision_engine._clip_mesh_at_z(
        local_mesh.vertices, local_mesh.faces, z
    )
    if clip_result is not None and not np.all(collisions):
        clip_v, clip_f = clip_result
        clip_hom = np.column_stack([clip_v, np.ones(len(clip_v))])
        clip_world_hom = (mat @ clip_hom.T).T
        clip_world_v = clip_world_hom[:, :3] / clip_world_hom[:, 3:4]

        # Build BVH from current chunk's clipped part
        clip_bvh = MeshBVH(vertices=clip_world_v, faces=clip_f)

        # --- Bbox early-out for clip BVH ---
        clip_mesh = clip_bvh.get_mesh()
        clip_bbox_min = clip_mesh.bounds[0]
        clip_bbox_max = clip_mesh.bounds[1]
        expanded_min = clip_bbox_min - holder_radius
        expanded_max = clip_bbox_max + holder_radius
        outside_bbox = np.any(holder_ends < expanded_min, axis=1) | np.any(holder_ends > expanded_max, axis=1)
        inside_idx = np.nonzero(~outside_bbox)[0]
        
        # Only check points that: (1) not already colliding with earlier chunks, (2) inside clip bbox
        remaining_idx = np.nonzero(~collisions)[0]
        if len(remaining_idx) > 0:
            # Intersect with inside_idx
            mask = np.isin(remaining_idx, inside_idx)
            final_idx = remaining_idx[mask]
            if len(final_idx) > 0:
                new_collisions = collision_engine.batch_check_poses_with_bvh(
                    pts_world[final_idx],
                    norms_world[final_idx],
                    clip_bvh,
                )
                collisions[final_idx[new_collisions]] = True

    return collisions


class GeometryApplicationService:
    @staticmethod
    def execute(
        job_id: str,
        file_bytes: bytes,
        job_mode: JobMode,
        job_settings: dict,
        machine_profile: dict,
        progress_callback: Callable[[StageProgressEvent], None] = None,
        is_cancelled: Callable[[], bool] = None
    ) -> Tuple[Dict[str, Any], list]:
        """
        Pure computation boundary for mesh processing and slicing.
        Returns:
            (result_payload, diagnostics_list)
        """
        diagnostics = []
        
        def emit(stage, progress, severity=None, status=None, code=None, message=None):
            if progress_callback:
                progress_callback(StageProgressEvent(
                    job_id=job_id,
                    stage=stage,
                    progress=progress,
                    severity=severity,
                    status=status,
                    code=code,
                    message=message
                ))

        def check_cancellation(stage: JobStage):
            if is_cancelled and is_cancelled():
                diagnostics.append(ValidationDiagnostic(
                    stage=stage,
                    severity=DiagnosticSeverity.WARNING,
                    status=DiagnosticStatus.FAIL,
                    code="X-001",
                    message="Job was cooperatively cancelled by user."
                ))
                raise JobCancelledError("Job was cooperatively cancelled.")
        
        try:
            emit(JobStage.MESH_VALIDATION, 0.0)
            check_cancellation(JobStage.MESH_VALIDATION)
            # 1. Load and Validate Mesh
            try:
                mesh = trimesh.load(io.BytesIO(file_bytes), file_type='stl')
                from mesh_structural_validator import validate_mesh_structure
                
                validated_mesh, raw_diags = validate_mesh_structure(mesh.vertices, mesh.faces)
                
                for d in raw_diags:
                    status = DiagnosticStatus.FAIL if d["severity"] == DiagnosticSeverity.ERROR else DiagnosticStatus.WARNING
                    diagnostics.append(ValidationDiagnostic(
                        stage=JobStage.MESH_VALIDATION,
                        severity=d["severity"],
                        status=status,
                        code=d["code"],
                        message=d["message"]
                    ))
                    
                mesh = validated_mesh
                if mesh is None:
                    # Execution halted by validator
                    return {}, diagnostics
                
                emit(JobStage.MESH_VALIDATION, 1.0)
                
            except Exception as e:
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.MESH_VALIDATION,
                    severity=DiagnosticSeverity.CRITICAL,
                    status=DiagnosticStatus.FAIL,
                    code="M-000",
                    message=f"Failed to load mesh: {str(e)}"
                ))
                return {}, diagnostics
                
            # Stop early if mesh validation has blocking errors
            val_result = ValidationResult(diagnostics=diagnostics)
            if val_result.is_blocking:
                return {}, diagnostics
                
            emit(JobStage.CANONICAL_FRAME, 0.0)
            check_cancellation(JobStage.CANONICAL_FRAME)
            # 2. Canonical Frame Alignment
            try:
                aligned_mesh, transform_mat = transform_utils.apply_canonical_transform(mesh)
                # Log transform applied
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.CANONICAL_FRAME,
                    severity=DiagnosticSeverity.INFO,
                    status=DiagnosticStatus.PASS,
                    code="C-001",
                    message="Canonical transform applied successfully."
                ))
                emit(JobStage.CANONICAL_FRAME, 1.0)
            except Exception as e:
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.CANONICAL_FRAME,
                    severity=DiagnosticSeverity.ERROR,
                    status=DiagnosticStatus.FAIL,
                    code="C-000",
                    message=f"Canonical transform failed: {str(e)}"
                ))
                return {}, diagnostics
                
            emit(JobStage.SECTIONING, 0.0)
            check_cancellation(JobStage.SECTIONING)
            # 3. Slicing — dispatch on job_mode
            layer_height = job_settings.get("layer_height", 0.2)
            bed_center_z = job_settings.get("bed_center_z", 0.0)
            
            try:
                if job_mode in (JobMode.THREE_AXIS, JobMode.INDEXED_MULTIDIRECTIONAL):
                    result, chunk_diagnostics, layers_data, chunks_data = GeometryApplicationService._execute_chunk_path(
                        job_id=job_id,
                        aligned_mesh=aligned_mesh,
                        job_mode=job_mode,
                        job_settings=job_settings,
                        machine_profile=machine_profile,
                        layer_height=layer_height,
                        bed_center_z=bed_center_z,
                    )
                    diagnostics.extend(chunk_diagnostics)
                else:
                    # Legacy fallback path for any other/unknown mode
                    export_bytes = io.BytesIO()
                    aligned_mesh.export(export_bytes, file_type='stl')
                    aligned_bytes = export_bytes.getvalue()
                    result = slicer_python.slice_mesh(aligned_bytes, layer_height, bed_center_z)
                    layers_data = []
                    chunks_data = []
                
                if "error" in result or not result:
                    # S-001 FAIL diagnostic already appended by _execute_chunk_path
                    # (extended into diagnostics via chunk_diagnostics above).
                    # For the legacy path, emit S-001 FAIL here (only if not already present).
                    if "error" in result:
                        has_s001_fail = any(
                            d.code == "S-001" and d.status == DiagnosticStatus.FAIL
                            for d in diagnostics
                        )
                        if not has_s001_fail:
                            diagnostics.append(ValidationDiagnostic(
                                stage=JobStage.SECTIONING,
                                severity=DiagnosticSeverity.ERROR,
                                status=DiagnosticStatus.FAIL,
                                code="S-001",
                                message=f"Slicing failed: {result.get('error', 'unknown error')}"
                            ))
                    emit(JobStage.SECTIONING, 1.0)
                    return {"toolpath_job": result}, diagnostics
                
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.INFO,
                    status=DiagnosticStatus.PASS,
                    code="S-001",
                    message="Slicing completed."
                ))
                emit(JobStage.SECTIONING, 1.0)
                
                # Handle legacy gcode_file
                if "gcode_file" in result and hasattr(result["gcode_file"], "read"):
                    result["gcode_file"].seek(0)
                    gcode_str = result["gcode_file"].read()
                    result["gcode_file"].close()
                    result["gcode_string"] = gcode_str
                    del result["gcode_file"]
                
                # Attach persistence data
                result["_layers_data"] = layers_data
                result["_chunks_data"] = chunks_data
                
                return {"toolpath_job": result}, diagnostics
                
            except Exception as e:
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.ERROR,
                    status=DiagnosticStatus.FAIL,
                    code="S-000",
                    message=f"Slicing failed: {str(e)}"
                ))
                return {}, diagnostics

        except JobCancelledError:
            # We gracefully return empty payload, but include the cancellation diagnostic which was already appended.
            return {"status": "cancelled"}, diagnostics

    @staticmethod
    def _execute_chunk_path(job_id, aligned_mesh, job_mode, job_settings, machine_profile, layer_height, bed_center_z):
        """
        Chunk-based slicing path for THREE_AXIS and INDEXED_MULTIDIRECTIONAL modes.
        Returns (result_dict, diagnostics, layers_data, chunks_data).
        """
        diagnostics = []
        layers_data = []
        chunks_data = []
        
        # --- Build slice planes ---
        planes = []
        if job_mode == JobMode.INDEXED_MULTIDIRECTIONAL:
            plane_configs = job_settings.get("slice_planes", [])
            for pc in plane_configs:
                try:
                    planes.append(SlicePlane(**pc))
                except Exception:
                    continue
        # THREE_AXIS: no planes → single chunk = whole mesh
        
        # --- Preflight planes ---
        for plane in planes:
            diagnostics.extend(preflight_slice_plane(aligned_mesh, plane))
        
        val_result = ValidationResult(diagnostics=diagnostics)
        if val_result.is_blocking:
            return {}, diagnostics, [], []
        
        # --- Build and subtract chunks ---
        chunks = build_capped_chunks(aligned_mesh, planes)
        chunks, sub_diags = subtract_later_chunks(job_id, chunks)
        diagnostics.extend(sub_diags)
        
        valid_chunks = [(i, c) for i, c in enumerate(chunks) if c is not None and not c.is_empty]
        if not valid_chunks:
            diagnostics.append(ValidationDiagnostic(
                stage=JobStage.SECTIONING,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.FAIL,
                code="S-002",
                message="No valid chunks produced from slice planes."
            ))
            return {}, diagnostics, [], []
        
        # --- Machine profile for collision ---
        limits = machine_profile.get("limits", {}) if isinstance(machine_profile, dict) else {}
        ranges = limits.get("ranges", {}) if isinstance(limits, dict) else {}
        profile = SlicerMachineProfile(
            nozzle_length=float(limits.get("nozzle_length", 40.0)) if limits else 40.0,
            nozzle_holder_radius=float(limits.get("nozzle_holder_radius", 5.0)) if limits else 5.0,
        )
        
        # Full-mesh BVH for collision; we filter by current_z (material below layer)
        part_bvh = MeshBVH(aligned_mesh.vertices, aligned_mesh.faces)
        collision_engine = CollisionEngine(profile, part_bvh, bed_center_z=bed_center_z)
        
        all_path_points = []  # (x, y, z, nx, ny, nz, layer_idx, feature_type, path_id)
        path_id_counter = 0
        global_layer_idx = 0
        
        # Cache for the combined printed-material BVH of all earlier chunks,
        # built once per chunk position (not per layer).
        earlier_chunks_bvh_cache: dict = {}

        for position, (chunk_idx, chunk_mesh) in enumerate(valid_chunks):
            # Determine slice plane for this chunk
            if chunk_idx == 0:
                plane = SlicePlane(
                    plane_origin=(0.0, 0.0, 0.0),
                    unit_normal=(0.0, 0.0, 1.0),
                    angle_pair=(0.0, 0.0),
                    angle_units="degrees",
                    rotation_convention="AC_TABLE",
                    local_x=(1.0, 0.0, 0.0),
                    local_y=(0.0, 1.0, 0.0),
                    source_frame="canonical"
                )
            else:
                plane = planes[chunk_idx - 1]
            
            # Align chunk to slice plane
            local_mesh, matrix, min_z, max_z = align_chunk_to_slice_plane(chunk_mesh.copy(), plane)
            
            chunk_data = {
                "chunk_idx": chunk_idx,
                "source_plane": {
                    "plane_origin": list(plane.plane_origin),
                    "unit_normal": list(plane.unit_normal),
                    "local_x": list(plane.local_x),
                    "local_y": list(plane.local_y),
                    "angle_pair": list(plane.angle_pair),
                    "angle_units": plane.angle_units,
                    "rotation_convention": plane.rotation_convention,
                    "source_frame": plane.source_frame
                },
                "transform_matrix": matrix,
                "layer_idx_min": global_layer_idx,
                "layer_idx_max": global_layer_idx,
                "min_z": float(min_z),
                "max_z": float(max_z),
                "triangle_count": len(local_mesh.faces),
                "storage_key": f"chunk_{chunk_idx}"
            }
            chunks_data.append(chunk_data)

            # Build cached printed-material BVH from all earlier chunks (world frame),
            # built once per chunk position — not per layer.
            if chunk_idx > 0 and chunk_idx not in earlier_chunks_bvh_cache:
                combined_v = []
                combined_f = []
                face_offset = 0
                for _, prev_mesh in valid_chunks[:chunk_idx]:
                    combined_v.append(prev_mesh.vertices)
                    combined_f.append(prev_mesh.faces + face_offset)
                    face_offset += len(prev_mesh.vertices)
                if combined_v:
                    earlier_chunks_bvh_cache[chunk_idx] = MeshBVH(
                        vertices=np.vstack(combined_v),
                        faces=np.vstack(combined_f),
                    )
                else:
                    earlier_chunks_bvh_cache[chunk_idx] = None

            # --- Layer schedule ---
            schedule = generate_layer_schedule(z_min=min_z, z_max=max_z, layer_height=layer_height)
            
            for z in schedule:
                segments = slice_mesh_at_z(local_mesh, z)
                polygons = reconstruct_polygons(segments)
                
                layers_data.append({
                    "layer_idx": global_layer_idx,
                    "z_height": float(z),
                    "thickness": float(layer_height),
                    "is_support": False
                })
                
                if polygons.is_empty:
                    global_layer_idx += 1
                    continue
                
                # --- Shells + Infill ---
                area_logic = AreaLogic(extrusion_width=0.4)
                if polygons.geom_type == 'MultiPolygon':
                    boundaries = list(polygons.geoms)
                else:
                    boundaries = [polygons]
                
                shells, infill_areas = area_logic.generate_shells_and_infill_area(boundaries, num_shells=2)

                # Collision paths: shells + infill (what is actually printed)
                infill_poly = polygons
                infill_lines = generate_line_infill(infill_poly, spacing=2.0, angle_degrees=45.0)
                collision_paths = []
                for shell in shells:
                    collision_paths.append(LineString(shell.exterior.coords))
                    for interior in shell.interiors:
                        collision_paths.append(LineString(interior.coords))
                for line in infill_lines:
                    collision_paths.append(line)

                # G-code paths: original section boundaries (world-frame fidelity)
                section_polygons = (
                    list(polygons.geoms)
                    if polygons.geom_type == 'MultiPolygon'
                    else [polygons]
                )
                gcode_paths = []
                for polygon in section_polygons:
                    gcode_paths.append(LineString(polygon.exterior.coords))
                    for interior in polygon.interiors:
                        gcode_paths.append(LineString(interior.coords))

                # All paths for G-code output: section boundaries + infill
                all_paths = gcode_paths + infill_lines

                # Collision paths: only inset shells (no infill, no section boundaries)
                if collision_paths:
                    ordered_collision = order_paths((0.0, 0.0), collision_paths)
                else:
                    ordered_collision = []

                if all_paths:
                    ordered = order_paths((0.0, 0.0), all_paths)
                else:
                    ordered = []

                holder_radius = profile.nozzle_holder_radius
                max_spacing = holder_radius / 2.0

                # Build local-to-world 4x4 matrix from the chunk transform.
                mat = np.array(matrix, dtype=float).reshape(4, 4)

                # --- Resample collision paths at spacing <= holder_radius/2 ---
                sampled = []  # list of (pts_local (N,3), n_samples)

                for path in ordered_collision:
                    coords = np.array(path.coords)
                    if len(coords) < 2:
                        continue
                    diffs = np.diff(coords, axis=0)
                    seg_lengths = np.sqrt((diffs ** 2).sum(axis=1))
                    cum_lengths = np.concatenate([[0.0], np.cumsum(seg_lengths)])
                    total_length = cum_lengths[-1]
                    if total_length == 0:
                        continue
                    n_samples = max(2, int(np.ceil(total_length / max_spacing)) + 1)
                    sample_d = np.linspace(0.0, total_length, n_samples)
                    xs = np.interp(sample_d, cum_lengths, coords[:, 0])
                    ys = np.interp(sample_d, cum_lengths, coords[:, 1])
                    zs = np.full(n_samples, z, dtype=float)
                    pts_local = np.column_stack([xs, ys, zs])
                    sampled.append((pts_local, n_samples))

                if sampled:
                    all_pts_local = np.vstack([s[0] for s in sampled])
                    # Local-space nozzle normal is (0, 0, 1).
                    all_norms_local = np.tile(
                        np.array([0.0, 0.0, 1.0]), (len(all_pts_local), 1)
                    )

                    # Transform local points to world (w=1 homogeneous).
                    pts_hom = np.column_stack(
                        [all_pts_local, np.ones(len(all_pts_local))]
                    )
                    pts_world_hom = (mat @ pts_hom.T).T
                    pts_world = pts_world_hom[:, :3] / pts_world_hom[:, 3:4]

                    # Transform normals to world (w=0, rotation only), then normalize.
                    norms_hom = np.column_stack(
                        [all_norms_local, np.zeros(len(all_pts_local))]
                    )
                    norms_world_hom = (mat @ norms_hom.T).T
                    norms_world = norms_world_hom[:, :3]
                    norms_world = norms_world / np.linalg.norm(
                        norms_world, axis=1, keepdims=True
                    )

                    # --- Collision check against printed material ---
                    if chunk_idx == 0:
                        # Horizontal plane: local == world for the base chunk.
                        collisions = collision_engine.batch_check_poses(
                            pts_world, norms_world, current_z=z
                        )
                    else:
                        # Printed material = all earlier chunks (world frame, cached BVH)
                        # UNION current chunk's already-printed part (clip by this layer, mapped to world).
                        # The earlier-chunks BVH is cached (built once per chunk, not per layer).
                        # Use batch_check_poses_with_bvh so the collision chain
                        # is exercised (test_f patches this method).
                        cached_bvh = earlier_chunks_bvh_cache.get(chunk_idx)
                        collisions = _check_chunk_ge_1_collision(
                            collision_engine,
                            pts_world,
                            norms_world,
                            local_mesh,
                            mat,
                            z,
                            profile,
                            cached_bvh,
                        )

                    if bool(np.any(collisions)):
                        collision_message = (
                            f"Collision detected on layer {global_layer_idx}: "
                            f"part collision. Change orientation or limit amplitude."
                        )
                        diagnostics.append(ValidationDiagnostic(
                            stage=JobStage.SECTIONING,
                            severity=DiagnosticSeverity.ERROR,
                            status=DiagnosticStatus.FAIL,
                            code="S-001",
                            message=collision_message
                        ))
                        return {"error": collision_message}, diagnostics, [], []

                # --- Append world-frame original path vertices ---
                # G-code fidelity: emit each ordered path's ORIGINAL
                # vertex sequence (ring edges must survive as
                # consecutive print moves); the dense resamples above
                # exist only for collision sampling.
                if all_paths:
                    ordered_gcode = order_paths((0.0, 0.0), all_paths)
                else:
                    ordered_gcode = []
                for path in ordered_gcode:
                    raw_coords = np.asarray(path.coords, dtype=float)
                    if raw_coords.shape[0] < 2:
                        continue
                    seg_steps = np.linalg.norm(
                        np.diff(raw_coords, axis=0), axis=1
                    )
                    keep = np.concatenate(
                        ([True], seg_steps > 1e-12)
                    )
                    vertex_coords = raw_coords[keep]
                    if vertex_coords.shape[0] < 2:
                        continue
                    zs_local = np.full(
                        vertex_coords.shape[0], z, dtype=float
                    )
                    pts_local = np.column_stack(
                        [
                            vertex_coords[:, 0],
                            vertex_coords[:, 1],
                            zs_local,
                        ]
                    )

                    # Transform local points to world (w=1 homogeneous).
                    pts_hom = np.column_stack(
                        [pts_local, np.ones(pts_local.shape[0])]
                    )
                    pts_world_hom = (mat @ pts_hom.T).T
                    pts_world_gcode = pts_world_hom[:, :3] / pts_world_hom[:, 3:4]

                    # Transform normal to world (w=0, rotation only),
                    # then normalize.
                    normal_hom = mat @ np.array([0.0, 0.0, 1.0, 0.0])
                    normal_world = normal_hom[:3] / np.linalg.norm(
                        normal_hom[:3]
                    )

                    for wx, wy, wz in pts_world_gcode:
                        all_path_points.append((
                            float(wx), float(wy), float(wz),
                            float(normal_world[0]),
                            float(normal_world[1]),
                            float(normal_world[2]),
                            global_layer_idx, "perimeter", path_id_counter
                        ))
                    path_id_counter += 1
                
                global_layer_idx += 1

            # Set layer_idx_max for this chunk after its layer loop completes
            chunk_data["layer_idx_max"] = global_layer_idx - 1
        
        # --- Generate G-code ---
        if all_path_points:
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
            generator = RotaryGCodeGenerator(settings, kinematics, e_multiplier=0.05, travel_threshold=1.5)
            
            path_points = [(px, py, pz, nx, ny, nz) for px, py, pz, nx, ny, nz, _, _, _ in all_path_points]
            gcode_str, _ = generator.generate(path_points)
        else:
            gcode_str = ""
        
        result = {
            "gcode_string": gcode_str,
            "layer_count": len(layers_data),
            "path_count": len(all_path_points),
        }
        
        return result, diagnostics, layers_data, chunks_data
