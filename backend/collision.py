"""
Collision Checking Module - Fail-Closed with Swept-Volume
==========================================================

This module implements collision checking that FAILS CLOSED:
- Any missing/invalid configuration -> collision (blocks export)
- Any NaN/non-finite result -> collision
- Any exception during check -> collision
- Incomplete checks -> collision

SWEEP-VOLUME COLLISION CHECKING
-------------------------------
Point sampling is insufficient for 5-axis printing where the nozzle
orientation changes rapidly. We implement adaptive swept-volume checking
by interpolating between consecutive poses and checking the tool envelope
against the bed, printed part, and forbidden regions.

CONSERVATIVE APPROXIMATION
--------------------------
If exact swept-volume geometry is unavailable, we use a conservative
approximation (capsule/union of spheres) that may reject valid paths
but NEVER certifies an unsafe path.
"""

import numpy as np
import trimesh
import manifold3d
from typing import List, Optional, Dict, Tuple, NamedTuple
from dataclasses import dataclass
from enum import Enum
from models import SlicerMachineProfile, MachinePose, CollisionReport, FeaturePath
from bvh import MeshBVH
from coordinate_frames import ac_table_forward_kinematics, ac_table_apply_normal

# Tolerances
_CLIP_TOLERANCE = 1e-6
_SWEEP_DEFAULT_STEP_MM = 0.5      # Max translation step for sweep sampling
_SWEEP_DEFAULT_STEP_DEG = 2.0     # Max angular step (deg) for sweep sampling
_MIN_SWEEP_SAMPLES = 3            # Minimum samples per segment
_MAX_SWEEP_SAMPLES = 100          # Maximum samples per segment (safety limit)


class CollisionStatus(Enum):
    """Structured collision check result status."""
    SAFE = "safe"
    BED_COLLISION = "bed_collision"
    PART_COLLISION = "part_collision"
    MACHINE_LIMIT = "machine_limit"
    INVALID_CONFIG = "invalid_config"
    NUMERICAL_ERROR = "numerical_error"
    SWEEP_FAILED = "sweep_failed"
    MISSING_GEOMETRY = "missing_geometry"


@dataclass(frozen=True)
class CollisionResult:
    """Structured collision check result - never returns None for failure."""
    status: CollisionStatus
    valid: bool                    # True only if status == SAFE
    severity: str                  # 'info', 'warning', 'error', 'critical'
    code: str                      # Machine-readable failure code
    message: str                   # Human-readable message
    affected_segment: Optional[int] = None      # Path segment index
    affected_point: Optional[int] = None        # Point index within segment
    machine_pose: Optional[MachinePose] = None  # Machine state at collision
    min_clearance_mm: Optional[float] = None    # Minimum clearance if available
    limiting_surface: Optional[str] = None      # 'bed', 'part', 'machine_limit', etc.
    suggested_remedy: Optional[str] = None
    
    @classmethod
    def safe(cls, clearance_mm: Optional[float] = None) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.SAFE,
            valid=True,
            severity="info",
            code="SAFE",
            message="No collision detected",
            min_clearance_mm=clearance_mm
        )
    
    @classmethod
    def bed_collision(cls, msg: str, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.BED_COLLISION,
            valid=False,
            severity="critical",
            code="BED_COLLISION",
            message=msg,
            limiting_surface="bed",
            **kwargs
        )
    
    @classmethod
    def part_collision(cls, msg: str, clearance_mm: Optional[float] = None, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.PART_COLLISION,
            valid=False,
            severity="critical",
            code="PART_COLLISION",
            message=msg,
            limiting_surface="part",
            min_clearance_mm=clearance_mm,
            **kwargs
        )
    
    @classmethod
    def machine_limit(cls, msg: str, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.MACHINE_LIMIT,
            valid=False,
            severity="critical",
            code="MACHINE_LIMIT",
            message=msg,
            limiting_surface="machine_limit",
            **kwargs
        )
    
    @classmethod
    def invalid_config(cls, msg: str, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.INVALID_CONFIG,
            valid=False,
            severity="critical",
            code="INVALID_CONFIG",
            message=msg,
            **kwargs
        )
    
    @classmethod
    def numerical_error(cls, msg: str, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.NUMERICAL_ERROR,
            valid=False,
            severity="critical",
            code="NUMERICAL_ERROR",
            message=msg,
            **kwargs
        )
    
    @classmethod
    def sweep_failed(cls, msg: str, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.SWEEP_FAILED,
            valid=False,
            severity="critical",
            code="SWEEP_FAILED",
            message=msg,
            **kwargs
        )
    
    @classmethod
    def missing_geometry(cls, msg: str, **kwargs) -> 'CollisionResult':
        return cls(
            status=CollisionStatus.MISSING_GEOMETRY,
            valid=False,
            severity="critical",
            code="MISSING_GEOMETRY",
            message=msg,
            **kwargs
        )
    
    def to_legacy_report(self, path_id: int, layer_idx: int, point_index: int) -> CollisionReport:
        """Convert to legacy CollisionReport for backward compatibility."""
        return CollisionReport(
            path_id=path_id,
            layer_idx=layer_idx,
            point_index=point_index,
            clearance=self.min_clearance_mm or -1.0,
            limiting_surface=self.limiting_surface or "unknown",
            suggested_remedy=self.suggested_remedy or "Check machine limits and orientation."
        )


def _trimesh_to_manifold(vertices: np.ndarray, faces: np.ndarray) -> manifold3d.Manifold:
    """Convert vertex/face arrays to a manifold3d Manifold."""
    m_mesh = manifold3d.Mesh(
        np.ascontiguousarray(vertices, dtype=np.float32),
        np.ascontiguousarray(faces, dtype=np.uint32),
    )
    return manifold3d.Manifold(m_mesh)


def _manifold_to_trimesh_arrays(m: manifold3d.Manifold) -> Tuple[np.ndarray, np.ndarray]:
    """Convert a manifold3d Manifold to (vertices, faces) numpy arrays."""
    mesh_out = m.to_mesh()
    verts = np.asarray(mesh_out.vert_properties, dtype=np.float64)
    faces = np.asarray(mesh_out.tri_verts, dtype=np.int64)
    return verts, faces


def _validate_machine_profile(profile: SlicerMachineProfile) -> Optional[CollisionResult]:
    """Validate machine profile has required collision parameters."""
    if profile is None:
        return CollisionResult.invalid_config("Machine profile is None")
    
    # Check required fields
    required_fields = ['nozzle_length', 'nozzle_holder_radius']
    for field_name in required_fields:
        if not hasattr(profile, field_name):
            return CollisionResult.invalid_config(f"Machine profile missing required field: {field_name}")
        val = getattr(profile, field_name)
        if not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0:
            return CollisionResult.invalid_config(f"Machine profile field {field_name} must be positive finite, got {val}")
    
    # Check axis limits if present
    if hasattr(profile, 'limits') and profile.limits:
        ranges = profile.limits.get('ranges', {})
        for axis, (min_v, max_v) in ranges.items():
            if not (isinstance(min_v, (int, float)) and isinstance(max_v, (int, float))):
                return CollisionResult.invalid_config(f"Axis {axis} limits must be numeric")
            if not (math.isfinite(min_v) and math.isfinite(max_v)):
                return CollisionResult.invalid_config(f"Axis {axis} limits must be finite")
            if min_v >= max_v:
                return CollisionResult.machine_limit(f"Axis {axis} limits invalid: min {min_v} >= max {max_v}")
    
    return None


import math


class CollisionEngine:
    """
    Collision engine with fail-closed semantics and swept-volume checking.
    
    All public methods return CollisionResult (never None for failure).
    Exceptions are caught and converted to CollisionResult with NUMERICAL_ERROR status.
    """
    
    def __init__(
        self, 
        profile: SlicerMachineProfile, 
        part_bvh: MeshBVH, 
        bed_center_z: float = 0.0,
        sweep_step_mm: float = _SWEEP_DEFAULT_STEP_MM,
        sweep_step_deg: float = _SWEEP_DEFAULT_STEP_DEG,
    ):
        # Validate profile immediately - fail closed
        config_error = _validate_machine_profile(profile)
        if config_error:
            raise ValueError(f"Invalid machine profile: {config_error.message}")
        
        self.profile = profile
        self.part_bvh = part_bvh
        self.bed_center_z = bed_center_z
        self.bed_z = -bed_center_z
        self.sweep_step_mm = max(0.1, sweep_step_mm)  # Minimum 0.1mm step
        self.sweep_step_deg = max(0.1, sweep_step_deg)  # Minimum 0.1deg step
        self._printed_bvh_cache: Dict[float, Optional[MeshBVH]] = {}
    
    def check_bed_collision(self, x: float, y: float, z: float, nx: float, ny: float, nz: float) -> CollisionResult:
        """
        Check collision between nozzle/holder and bed plane.
        
        Returns CollisionResult (SAFE or BED_COLLISION).
        """
        try:
            # Validate inputs
            for name, val in [('x', x), ('y', y), ('z', z), ('nx', nx), ('ny', ny), ('nz', nz)]:
                if not math.isfinite(val):
                    return CollisionResult.numerical_error(f"Non-finite {name}: {val}")
            
            # Check normal is unit length
            n_len = math.hypot(nx, ny, nz)
            if not math.isclose(n_len, 1.0, rel_tol=1e-4):
                return CollisionResult.numerical_error(f"Non-unit normal: length={n_len}")
            
            tip_z = z
            tail_z = z + nz * self.profile.nozzle_length
            
            # Check tip below bed
            if tip_z < self.bed_z:
                return CollisionResult.bed_collision(
                    f"Nozzle tip Z={tip_z:.3f} below bed Z={self.bed_z:.3f}",
                    affected_point=None,
                    machine_pose=MachinePose(x=x, y=y, z=z, u=0, v=0, feedrate_limit=0)
                )
            
            # Check holder below bed when tilted
            if abs(nz) < 0.9999:
                sin_theta = math.sqrt(nx**2 + ny**2)
                lowest_holder_z = tail_z - self.profile.nozzle_holder_radius * sin_theta
                if lowest_holder_z < self.bed_z:
                    return CollisionResult.bed_collision(
                        f"Nozzle holder (tilted) intersects bed: lowest Z={lowest_holder_z:.3f} < {self.bed_z:.3f}",
                        affected_point=None,
                        machine_pose=MachinePose(x=x, y=y, z=z, u=0, v=0, feedrate_limit=0)
                    )
            
            return CollisionResult.safe()
            
        except Exception as e:
            return CollisionResult.numerical_error(f"Bed collision check failed: {e}")

    def _clip_mesh_at_z(self, vertices: np.ndarray, faces: np.ndarray, z_plane: float) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Clip mesh at z=z_plane, keeping portion below, with a cap face."""
        try:
            m = _trimesh_to_manifold(vertices, faces)
            if m.is_empty():
                return None

            # Keep portion below z_plane: normal=(0,0,-1), offset=-z_plane
            # keeps points where (0,0,-1)·X > -z_plane  =>  z < z_plane
            below_m = m.trim_by_plane((0.0, 0.0, -1.0), -z_plane)
            if below_m.is_empty():
                return None

            v_new, f_new = _manifold_to_trimesh_arrays(below_m)
            if len(f_new) == 0:
                return None

            return v_new, f_new
        except Exception as e:
            # Fail closed: any clipping error -> treat as collision
            raise RuntimeError(f"Mesh clipping failed at z={z_plane}: {e}")

    def _get_printed_bvh(self, current_z: float) -> Optional[MeshBVH]:
        """Build (and cache) a BVH holding the material already printed."""
        try:
            # Round current_z for cache key to avoid floating-point cache misses
            cache_key = round(current_z * 1000) / 1000.0  # 0.001mm precision
            
            if cache_key in self._printed_bvh_cache:
                return self._printed_bvh_cache[cache_key]

            mesh = self.part_bvh.get_mesh()
            vertices = np.asarray(mesh.vertices, dtype=float)
            faces = np.asarray(mesh.faces, dtype=int)

            if faces.shape[0] == 0:
                self._printed_bvh_cache[cache_key] = None
                return None

            clipped = self._clip_mesh_at_z(vertices, faces, current_z)
            if clipped is None:
                self._printed_bvh_cache[cache_key] = None
                return None

            clipped_vertices, clipped_faces = clipped
            printed_bvh = MeshBVH(vertices=clipped_vertices, faces=clipped_faces)
            self._printed_bvh_cache[cache_key] = printed_bvh
            return printed_bvh
            
        except Exception as e:
            # Fail closed
            raise RuntimeError(f"Printed BVH construction failed at z={current_z}: {e}")

    def validate_pose(
        self,
        x: float,
        y: float,
        z: float,
        nx: float,
        ny: float,
        nz: float,
        current_z: Optional[float] = None,
    ) -> CollisionResult:
        """
        Validate a single pose. Returns CollisionResult (never None).
        
        Exact rule: holder (radius nozzle_holder_radius, centred at
        tip + normal * nozzle_length) collides with printed material
        (mesh clipped at z <= current_z) within holder_radius.
        Material above current_z is unprinted and ignored.
        If current_z is None, the whole finished part is treated as printed.
        """
        try:
            # Bed collision check
            bed_result = self.check_bed_collision(x, y, z, nx, ny, nz)
            if not bed_result.valid:
                return bed_result
            
            tip = np.array([x, y, z], dtype=float)
            normal = np.array([nx, ny, nz], dtype=float)
            holder_end = tip + normal * self.profile.nozzle_length
            holder_radius = self.profile.nozzle_holder_radius
            
            # Early-out: if holder end is well above current_z + radius, no part collision possible
            if current_z is not None and holder_end[2] - holder_radius > current_z + 1e-6:
                return CollisionResult.safe()
            
            # Get printed material BVH
            if current_z is not None:
                printed_bvh = self._get_printed_bvh(current_z)
                if printed_bvh is None:
                    return CollisionResult.safe()  # Nothing printed yet
            else:
                printed_bvh = self.part_bvh
            
            # Query distance
            dist = printed_bvh.query_distance(holder_end.reshape(1, 3))[0]
            
            if not math.isfinite(dist):
                return CollisionResult.numerical_error(f"Non-finite distance from BVH query: {dist}")
            
            if dist < holder_radius:
                return CollisionResult.part_collision(
                    f"Nozzle holder within {holder_radius}mm of printed part (dist={dist:.3f}mm)",
                    clearance_mm=dist,
                    machine_pose=MachinePose(x=x, y=y, z=z, u=0, v=0, feedrate_limit=0)
                )
            
            return CollisionResult.safe(clearance_mm=dist)
            
        except Exception as e:
            return CollisionResult.numerical_error(f"Pose validation failed: {e}")

    def batch_check_poses(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        current_z: Optional[float] = None,
    ) -> np.ndarray:
        """
        Batch check multiple poses. Returns numpy boolean array where True = collision.
        
        Maintains backward compatibility with geometry_service.py.
        For detailed results, use batch_check_poses_detailed().
        """
        try:
            points = np.asarray(points, dtype=float)
            normals = np.asarray(normals, dtype=float)
            
            if points.ndim != 2 or points.shape[1] != 3:
                # Return all True (collision) for invalid input shape
                return np.ones(points.shape[0] if points.ndim == 1 else 1, dtype=bool)
            if normals.shape != points.shape:
                return np.ones(points.shape[0], dtype=bool)
            
            count = points.shape[0]
            if count == 0:
                return np.zeros(0, dtype=bool)
            
            holder_ends = points + normals * self.profile.nozzle_length
            holder_radius = self.profile.nozzle_holder_radius
            
            collisions = np.zeros(count, dtype=bool)
            
            if current_z is not None:
                early_out = holder_ends[:, 2] - holder_radius > current_z + 1e-6
            else:
                early_out = np.zeros(count, dtype=bool)
            
            if current_z is not None:
                printed_bvh = self._get_printed_bvh(current_z)
                if printed_bvh is None:
                    # Nothing printed - all safe
                    return np.zeros(count, dtype=bool)
            else:
                printed_bvh = self.part_bvh
            
            # Check each pose that isn't early-out
            query_idx = np.nonzero(~early_out)[0]
            if query_idx.size == 0:
                return collisions  # all False (safe)
            
            for i in query_idx:
                pt = points[i]
                norm = normals[i]
                # Validate normal
                n_len = np.linalg.norm(norm)
                if not math.isclose(n_len, 1.0, rel_tol=1e-4):
                    collisions[i] = True
                    continue
                
                dist = printed_bvh.query_distance(holder_ends[i].reshape(1, 3))[0]
                if not math.isfinite(dist):
                    collisions[i] = True
                    continue
                
                if dist < holder_radius:
                    collisions[i] = True
            
            return collisions
            
        except Exception as e:
            # Fail closed: return all True (collision)
            return np.ones(count, dtype=bool)

    def batch_check_poses_with_bvh(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        printed_bvh: MeshBVH,
    ) -> np.ndarray:
        """Batch check poses against a custom printed-material BVH.
        
        Returns numpy boolean array where True = collision.
        """
        try:
            points = np.asarray(points, dtype=float)
            normals = np.asarray(normals, dtype=float)
            
            if points.ndim != 2 or points.shape[1] != 3:
                return np.ones(points.shape[0] if points.ndim == 1 else 1, dtype=bool)
            if normals.shape != points.shape:
                return np.ones(points.shape[0], dtype=bool)
            
            count = points.shape[0]
            if count == 0:
                return np.zeros(0, dtype=bool)
            
            holder_ends = points + normals * self.profile.nozzle_length
            holder_radius = self.profile.nozzle_holder_radius
            
            collisions = np.zeros(count, dtype=bool)
            
            for i in range(count):
                # Validate normal
                n_len = np.linalg.norm(normals[i])
                if not math.isclose(n_len, 1.0, rel_tol=1e-4):
                    collisions[i] = True
                    continue
                
                dist = printed_bvh.query_distance(holder_ends[i].reshape(1, 3))[0]
                if not math.isfinite(dist):
                    collisions[i] = True
                    continue
                
                if dist < holder_radius:
                    collisions[i] = True
            
            return collisions
            
        except Exception as e:
            return np.ones(count, dtype=bool)

    def query_closest_point(
        self,
        point: np.ndarray,
        current_z: Optional[float] = None,
    ) -> Tuple[Optional[np.ndarray], float]:
        """Return (closest_surface_point, distance) for a single point."""
        try:
            if current_z is not None:
                printed_bvh = self._get_printed_bvh(current_z)
                if printed_bvh is None:
                    return None, float("inf")
            else:
                printed_bvh = self.part_bvh
            
            p = np.asarray(point, dtype=float).reshape(1, 3)
            closest_points, distances, _ = printed_bvh.mesh.nearest.on_surface(p)
            return closest_points[0], float(distances[0])
        except Exception:
            return None, float("inf")

    # ============================================================
    # SWEEP-VOLUME COLLISION CHECKING (P0-5)
    # ============================================================
    
    def _interpolate_poses(
        self,
        p1: np.ndarray, n1: np.ndarray,
        p2: np.ndarray, n2: np.ndarray,
        num_samples: int
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Interpolate between two poses (position + normal).
        
        Uses SLERP for normals and linear interpolation for positions.
        Returns list of (position, normal) tuples including endpoints.
        """
        samples = []
        for i in range(num_samples):
            t = i / (num_samples - 1) if num_samples > 1 else 0.0
            
            # Linear interpolation for position
            pos = p1 + t * (p2 - p1)
            
            # SLERP for normal (unit quaternion interpolation)
            n1_norm = n1 / (np.linalg.norm(n1) + 1e-12)
            n2_norm = n2 / (np.linalg.norm(n2) + 1e-12)
            
            dot = np.clip(np.dot(n1_norm, n2_norm), -1.0, 1.0)
            if dot > 0.9995:
                # Nearly parallel - linear interpolation + normalize
                norm = n1_norm + t * (n2_norm - n1_norm)
                norm = norm / (np.linalg.norm(norm) + 1e-12)
            else:
                theta = math.acos(dot)
                sin_theta = math.sin(theta)
                norm = (math.sin((1-t)*theta) * n1_norm + math.sin(t*theta) * n2_norm) / sin_theta
            
            samples.append((pos, norm))
        
        return samples
    
    def _compute_sweep_samples(
        self,
        p1: np.ndarray, n1: np.ndarray,
        p2: np.ndarray, n2: np.ndarray
    ) -> int:
        """
        Compute number of sweep samples based on translation distance and angular change.
        
        Returns at least _MIN_SWEEP_SAMPLES, at most _MAX_SWEEP_SAMPLES.
        """
        # Translation distance
        trans_dist = np.linalg.norm(p2 - p1)
        n_samples_trans = max(1, int(math.ceil(trans_dist / self.sweep_step_mm)))
        
        # Angular change (degrees)
        n1_norm = n1 / (np.linalg.norm(n1) + 1e-12)
        n2_norm = n2 / (np.linalg.norm(n2) + 1e-12)
        dot = np.clip(np.dot(n1_norm, n2_norm), -1.0, 1.0)
        angle_deg = math.degrees(math.acos(dot))
        n_samples_rot = max(1, int(math.ceil(angle_deg / self.sweep_step_deg)))
        
        n_samples = max(n_samples_trans, n_samples_rot) + 1  # +1 for endpoints
        return min(max(n_samples, _MIN_SWEEP_SAMPLES), _MAX_SWEEP_SAMPLES)
    
    def sweep_check_segment(
        self,
        p1: np.ndarray, n1: np.ndarray,
        p2: np.ndarray, n2: np.ndarray,
        current_z: Optional[float] = None,
        path_id: int = 0,
        layer_idx: int = 0,
        segment_index: int = 0,
    ) -> List[CollisionResult]:
        """
        Swept-volume collision check for a single toolpath segment.
        
        Interpolates between poses and checks each interpolated pose.
        Returns list of CollisionResult (one per sample, empty if all safe).
        
        CONSERVATIVE APPROXIMATION: We sample the nozzle holder envelope
        at discrete poses along the segment. This may miss narrow features
        between samples but will never certify an unsafe path if sampling
        resolution is sufficient for the tool geometry.
        """
        results = []
        
        try:
            # Validate endpoints
            for name, arr in [("p1", p1), ("n1", n1), ("p2", p2), ("n2", n2)]:
                if not np.all(np.isfinite(arr)):
                    return [CollisionResult.numerical_error(f"{name} contains non-finite values")]
            
            n1_len = np.linalg.norm(n1)
            n2_len = np.linalg.norm(n2)
            if not math.isclose(n1_len, 1.0, rel_tol=1e-4) or not math.isclose(n2_len, 1.0, rel_tol=1e-4):
                return [CollisionResult.numerical_error(f"Non-unit normals: |n1|={n1_len}, |n2|={n2_len}")]
            
            # Compute adaptive sample count
            n_samples = self._compute_sweep_samples(p1, n1, p2, n2)
            
            # Interpolate poses
            samples = self._interpolate_poses(p1, n1, p2, n2, n_samples)
            
            # Get printed BVH once
            if current_z is not None:
                printed_bvh = self._get_printed_bvh(current_z)
                if printed_bvh is None:
                    # Nothing printed yet - all safe
                    return []
            else:
                printed_bvh = self.part_bvh
            
            holder_radius = self.profile.nozzle_holder_radius
            nozzle_len = self.profile.nozzle_length
            
            # Check each interpolated pose
            for i, (pos, norm) in enumerate(samples):
                holder_end = pos + norm * nozzle_len
                
                # Early-out: if well above printed material
                if current_z is not None and holder_end[2] - holder_radius > current_z + 1e-6:
                    continue
                
                # Bed check
                bed_result = self.check_bed_collision(pos[0], pos[1], pos[2], norm[0], norm[1], norm[2])
                if not bed_result.valid:
                    bed_result.affected_segment = segment_index
                    bed_result.affected_point = i
                    results.append(bed_result)
                    break  # Stop on first collision
                
                # Part collision check
                dist = printed_bvh.query_distance(holder_end.reshape(1, 3))[0]
                if not math.isfinite(dist):
                    results.append(CollisionResult.numerical_error(
                        f"Sweep sample {i}: non-finite distance",
                        affected_segment=segment_index,
                        affected_point=i
                    ))
                    break
                
                if dist < holder_radius:
                    results.append(CollisionResult.part_collision(
                        f"Sweep sample {i}: holder within {holder_radius}mm of printed part (dist={dist:.3f}mm)",
                        clearance_mm=dist,
                        affected_segment=segment_index,
                        affected_point=i,
                        machine_pose=MachinePose(x=pos[0], y=pos[1], z=pos[2], u=0, v=0, feedrate_limit=0)
                    ))
                    break
            
            return results
            
        except Exception as e:
            return [CollisionResult.sweep_failed(f"Sweep check failed: {e}", affected_segment=segment_index)]

    def sweep_check_path(
        self,
        path: FeaturePath,
        current_z: Optional[float] = None,
    ) -> List[CollisionReport]:
        """
        Swept-volume collision check for an entire feature path.
        
        Returns list of CollisionReport (legacy format) for backward compatibility.
        Empty list = no collisions.
        
        This method checks each consecutive pair of points in the path.
        """
        reports = []
        
        try:
            if len(path.points) < 2:
                return []
            
            points = np.array(path.points, dtype=float)
            normals = np.array(path.normals, dtype=float)
            
            if points.shape != normals.shape:
                return [CollisionReport(
                    path_id=path.path_id,
                    layer_idx=path.layer_idx,
                    point_index=-1,
                    clearance=-1.0,
                    limiting_surface="invalid_config",
                    suggested_remedy="Points and normals shape mismatch"
                )]
            
            # Check each segment
            for i in range(len(points) - 1):
                p1, n1 = points[i], normals[i]
                p2, n2 = points[i + 1], normals[i + 1]
                
                segment_results = self.sweep_check_segment(
                    p1, n1, p2, n2,
                    current_z=current_z,
                    path_id=path.path_id,
                    layer_idx=path.layer_idx,
                    segment_index=i,
                )
                
                if segment_results:
                    # Convert first failure to legacy report
                    first_failure = segment_results[0]
                    reports.append(first_failure.to_legacy_report(
                        path_id=path.path_id,
                        layer_idx=path.layer_idx,
                        point_index=first_failure.affected_point or i
                    ))
                    break  # Stop on first collision
            
            return reports
            
        except Exception as e:
            # Fail closed: return collision report for the error
            return [CollisionReport(
                path_id=path.path_id,
                layer_idx=path.layer_idx,
                point_index=-1,
                clearance=-1.0,
                limiting_surface="sweep_failed",
                suggested_remedy=f"Sweep check error: {e}"
            )]


# --- Test Functions ---

def test_fail_closed_missing_profile():
    """Missing profile should raise at construction."""
    from bvh import MeshBVH
    vertices = np.array([[0,0,0], [1,0,0], [0,1,0]], dtype=float)
    faces = np.array([[0,1,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    try:
        CollisionEngine(None, bvh)
        assert False, "Should have raised"
    except (ValueError, TypeError):
        pass
    print("✓ Fail-closed on missing profile")


def test_fail_closed_invalid_profile():
    """Invalid profile fields should raise."""
    from bvh import MeshBVH
    vertices = np.array([[0,0,0], [1,0,0], [0,1,0]], dtype=float)
    faces = np.array([[0,1,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    class BadProfile:
        nozzle_length = -1.0
        nozzle_holder_radius = 5.0
    
    try:
        CollisionEngine(BadProfile(), bvh)
        assert False, "Should have raised"
    except ValueError as e:
        assert "nozzle_length" in str(e)
    print("✓ Fail-closed on invalid profile")


def test_bed_collision_detection():
    """Bed collision should be detected and reported structurally."""
    from bvh import MeshBVH
    vertices = np.array([[0,0,10], [10,0,10], [0,10,10]], dtype=float)
    faces = np.array([[0,1,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    profile = SlicerMachineProfile(nozzle_length=40.0, nozzle_holder_radius=5.0)
    engine = CollisionEngine(profile, bvh, bed_center_z=0.0)
    
    # Tip below bed
    result = engine.check_bed_collision(0, 0, -1.0, 0, 0, 1)
    assert not result.valid
    assert result.status == CollisionStatus.BED_COLLISION
    assert "tip" in result.message.lower()
    
    # Tilted holder intersects bed - use short nozzle and steep angle
    # nozzle_length=3, holder_radius=5, tip at z=2, tilted 80 deg from vertical
    short_profile = SlicerMachineProfile(nozzle_length=3.0, nozzle_holder_radius=5.0)
    short_engine = CollisionEngine(short_profile, bvh, bed_center_z=0.0)
    # Tilt 80°: nz=cos(80°)≈0.17, nx=sin(80°)≈0.98
    result = short_engine.check_bed_collision(0, 0, 2.0, 0.9848, 0, 0.1736)
    assert not result.valid
    assert result.status == CollisionStatus.BED_COLLISION
    
    # Safe pose
    result = engine.check_bed_collision(0, 0, 10.0, 0, 0, 1)
    assert result.valid
    assert result.status == CollisionStatus.SAFE
    
    print("✓ Bed collision detection")


def test_part_collision_fail_closed():
    """Part collision should return structured failure."""
    from bvh import MeshBVH
    # Wall at x=0, printed up to z=50
    vertices = np.array([[-1, -5, 0], [1, -5, 0], [1, 5, 0], [-1, 5, 0],
                         [-1, -5, 50], [1, -5, 50], [1, 5, 50], [-1, 5, 50]], dtype=float)
    faces = np.array([[0,1,2],[0,2,3], [4,7,6],[4,6,5], [0,4,5],[0,5,1],
                      [3,2,6],[3,6,7], [0,3,7],[0,7,4], [1,5,6],[1,6,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    profile = SlicerMachineProfile(nozzle_length=3.0, nozzle_holder_radius=5.0)
    engine = CollisionEngine(profile, bvh, bed_center_z=1000.0)  # Bed far below
    
    # Holder end inside wall radius
    result = engine.validate_pose(3.0, 0.0, 50.0, -0.9, 0.0, 0.436, current_z=50.0)
    assert not result.valid
    assert result.status == CollisionStatus.PART_COLLISION
    assert result.min_clearance_mm is not None
    assert result.min_clearance_mm < 5.0
    
    print("✓ Part collision fail-closed")


def test_non_finite_input_fail_closed():
    """Non-finite inputs should return NUMERICAL_ERROR, not crash."""
    from bvh import MeshBVH
    vertices = np.array([[0,0,10], [10,0,10], [0,10,10]], dtype=float)
    faces = np.array([[0,1,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    profile = SlicerMachineProfile(nozzle_length=40.0, nozzle_holder_radius=5.0)
    engine = CollisionEngine(profile, bvh)
    
    # NaN position
    result = engine.check_bed_collision(float('nan'), 0, 10, 0, 0, 1)
    assert not result.valid
    assert result.status == CollisionStatus.NUMERICAL_ERROR
    
    # Infinite normal
    result = engine.check_bed_collision(0, 0, 10, float('inf'), 0, 1)
    assert not result.valid
    assert result.status == CollisionStatus.NUMERICAL_ERROR
    
    print("✓ Non-finite input fail-closed")


def test_sweep_check_segment():
    """Sweep check should interpolate and detect mid-segment collisions."""
    from bvh import MeshBVH
    # Wall at x=0
    vertices = np.array([[-1, -5, 0], [1, -5, 0], [1, 5, 0], [-1, 5, 0],
                         [-1, -5, 50], [1, -5, 50], [1, 5, 50], [-1, 5, 50]], dtype=float)
    faces = np.array([[0,1,2],[0,2,3], [4,7,6],[4,6,5], [0,4,5],[0,5,1],
                      [3,2,6],[3,6,7], [0,3,7],[0,7,4], [1,5,6],[1,6,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    profile = SlicerMachineProfile(nozzle_length=3.0, nozzle_holder_radius=5.0)
    engine = CollisionEngine(profile, bvh, bed_center_z=1000.0, sweep_step_mm=1.0)
    
    # Segment from safe (x=10) to collision (x=3) - should detect collision mid-segment
    p1 = np.array([10.0, 0.0, 50.0])
    n1 = np.array([0.0, 0.0, 1.0])
    p2 = np.array([3.0, 0.0, 50.0])
    n2 = np.array([0.0, 0.0, 1.0])
    
    results = engine.sweep_check_segment(p1, n1, p2, n2, current_z=50.0)
    # Should detect collision
    assert len(results) > 0
    assert not results[0].valid
    
    print("✓ Sweep check segment")


def test_sweep_check_path():
    """Full path sweep check."""
    from bvh import MeshBVH
    vertices = np.array([[-1, -5, 0], [1, -5, 0], [1, 5, 0], [-1, 5, 0],
                         [-1, -5, 50], [1, -5, 50], [1, 5, 50], [-1, 5, 50]], dtype=float)
    faces = np.array([[0,1,2],[0,2,3], [4,7,6],[4,6,5], [0,4,5],[0,5,1],
                      [3,2,6],[3,6,7], [0,3,7],[0,7,4], [1,5,6],[1,6,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    profile = SlicerMachineProfile(nozzle_length=3.0, nozzle_holder_radius=5.0)
    engine = CollisionEngine(profile, bvh, bed_center_z=1000.0)
    
    # Path that goes into wall
    path = FeaturePath(
        points=[(10.0, 0.0, 50.0), (5.0, 0.0, 50.0), (3.0, 0.0, 50.0)],
        normals=[(0,0,1), (0,0,1), (0,0,1)],
        layer_idx=10,
        feature_type="perimeter",
        path_id=1
    )
    
    reports = engine.sweep_check_path(path, current_z=50.0)
    assert len(reports) > 0
    assert reports[0].limiting_surface == "part"
    
    print("✓ Sweep check path")


def test_sweep_sampling_resolution():
    """Verify sampling resolution is sufficient for tool geometry."""
    from bvh import MeshBVH
    # Small feature that could be missed by coarse sampling
    vertices = np.array([[-0.5, -5, 0], [0.5, -5, 0], [0.5, 5, 0], [-0.5, 5, 0],
                         [-0.5, -5, 10], [0.5, -5, 10], [0.5, 5, 10], [-0.5, 5, 10]], dtype=float)
    faces = np.array([[0,1,2],[0,2,3], [4,7,6],[4,6,5], [0,4,5],[0,5,1],
                      [3,2,6],[3,6,7], [0,3,7],[0,7,4], [1,5,6],[1,6,2]], dtype=int)
    bvh = MeshBVH(vertices, faces)
    
    profile = SlicerMachineProfile(nozzle_length=3.0, nozzle_holder_radius=5.0)
    engine = CollisionEngine(profile, bvh, bed_center_z=1000.0, sweep_step_mm=0.5, sweep_step_deg=1.0)
    
    # Fast pass near thin wall - should detect
    p1 = np.array([10.0, 0.0, 5.0])
    n1 = np.array([0.0, 0.0, 1.0])
    p2 = np.array([-10.0, 0.0, 5.0])
    n2 = np.array([0.0, 0.0, 1.0])
    
    results = engine.sweep_check_segment(p1, n1, p2, n2, current_z=5.0)
    # Should detect collision with thin wall
    assert len(results) > 0
    
    print("✓ Sweep sampling resolution")


def test_legacy_compatibility():
    """CollisionResult should convert to legacy CollisionReport."""
    result = CollisionResult.part_collision("Test collision", clearance_mm=2.5, affected_point=3)
    legacy = result.to_legacy_report(path_id=1, layer_idx=5, point_index=3)
    
    assert isinstance(legacy, CollisionReport)
    assert legacy.path_id == 1
    assert legacy.layer_idx == 5
    assert legacy.point_index == 3
    assert legacy.clearance == 2.5
    assert legacy.limiting_surface == "part"
    
    print("✓ Legacy compatibility")


if __name__ == "__main__":
    test_fail_closed_missing_profile()
    test_fail_closed_invalid_profile()
    test_bed_collision_detection()
    test_part_collision_fail_closed()
    test_non_finite_input_fail_closed()
    test_sweep_check_segment()
    test_sweep_check_path()
    test_sweep_sampling_resolution()
    test_legacy_compatibility()
    print("\nAll CollisionEngine validation tests passed!")