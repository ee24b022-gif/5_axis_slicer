import numpy as np
import trimesh
import manifold3d
from typing import List, Optional, Dict, Tuple
from models import SlicerMachineProfile, MachinePose, CollisionReport, FeaturePath
from bvh import MeshBVH

# Small tolerance applied when deciding whether a vertex sits at the clip plane.
_CLIP_TOLERANCE = 1e-6


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


class CollisionEngine:
    def __init__(self, profile: SlicerMachineProfile, part_bvh: MeshBVH, bed_center_z: float = 0.0):
        self.profile = profile
        self.part_bvh = part_bvh
        self.bed_center_z = bed_center_z
        self.bed_z = -bed_center_z
        self._printed_bvh_cache: Dict[float, Optional[MeshBVH]] = {}

    def check_bed_collision(self, x: float, y: float, z: float, nx: float, ny: float, nz: float) -> bool:
        tip_z = z
        tail_z = z + nz * self.profile.nozzle_length
        if tip_z < self.bed_z or tail_z < self.bed_z:
            return True
        if abs(nz) < 0.9999:
            sin_theta = np.sqrt(nx**2 + ny**2)
            lowest_holder_z = tail_z - self.profile.nozzle_holder_radius * sin_theta
            if lowest_holder_z < self.bed_z:
                return True
        return False

    def _clip_mesh_at_z(self, vertices: np.ndarray, faces: np.ndarray, z_plane: float) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Clip mesh at z=z_plane, keeping portion below, with a cap face.

        Uses manifold3d trim_by_plane for a watertight, volume-conserving clip.

        Returns (clipped_vertices, clipped_faces) or None if nothing below z_plane.
        """
        m = _trimesh_to_manifold(vertices, faces)
        if m.is_empty():
            return None

        # Keep the portion below z_plane: normal=(0,0,-1), offset=-z_plane
        # keeps points where (0,0,-1)·X > -z_plane  =>  z < z_plane
        below_m = m.trim_by_plane((0.0, 0.0, -1.0), -z_plane)
        if below_m.is_empty():
            return None

        v_new, f_new = _manifold_to_trimesh_arrays(below_m)
        if len(f_new) == 0:
            return None

        return v_new, f_new

    def _get_printed_bvh(self, current_z: float) -> Optional[MeshBVH]:
        """Build (and cache) a BVH holding the material already printed.

        Printed material = mesh clipped at z=current_z (keep below, add cap).
        Triangles crossing the plane are CUT, not discarded.
        Returns None when nothing is printed at/below this height.
        """
        if current_z in self._printed_bvh_cache:
            return self._printed_bvh_cache[current_z]

        mesh = self.part_bvh.get_mesh()
        vertices = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=int)

        if faces.shape[0] == 0:
            self._printed_bvh_cache[current_z] = None
            return None

        clipped = self._clip_mesh_at_z(vertices, faces, current_z)
        if clipped is None:
            self._printed_bvh_cache[current_z] = None
            return None

        clipped_vertices, clipped_faces = clipped
        printed_bvh = MeshBVH(vertices=clipped_vertices, faces=clipped_faces)
        self._printed_bvh_cache[current_z] = printed_bvh
        return printed_bvh

    def validate_pose(
        self,
        x: float,
        y: float,
        z: float,
        nx: float,
        ny: float,
        nz: float,
        current_z: Optional[float] = None,
    ) -> Optional[str]:
        """Returns "bed" or "part" on collision, or None if safe.

        Exact rule: holder (radius nozzle_holder_radius, centred at
        tip + normal * nozzle_length) collides with printed material
        (mesh clipped at z <= current_z) within holder_radius.
        Material above current_z is unprinted and ignored.
        If current_z is None, the whole finished part is treated as printed.
        """
        if self.check_bed_collision(x, y, z, nx, ny, nz):
            return "bed"

        tip = np.array([x, y, z], dtype=float)
        normal = np.array([nx, ny, nz], dtype=float)
        holder_end = tip + normal * self.profile.nozzle_length
        holder_radius = self.profile.nozzle_holder_radius

        if current_z is not None and holder_end[2] - holder_radius > current_z:
            return None

        if current_z is not None:
            printed_bvh = self._get_printed_bvh(current_z)
            if printed_bvh is None:
                return None
        else:
            printed_bvh = self.part_bvh

        dist = printed_bvh.query_distance(holder_end.reshape(1, 3))[0]
        if dist < holder_radius:
            return "part"
        return None

    def batch_check_poses(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        current_z: Optional[float] = None,
    ) -> np.ndarray:
        points = np.asarray(points, dtype=float)
        normals = np.asarray(normals, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError(
                f"batch_check_poses: points must have shape (N, 3), got {points.shape}"
            )
        if normals.shape != points.shape:
            raise ValueError(
                f"batch_check_poses: normals must match points shape {points.shape}, "
                f"got {normals.shape}"
            )
        count = points.shape[0]
        collisions = np.zeros(count, dtype=bool)
        if count == 0:
            return collisions

        holder_ends = points + normals * self.profile.nozzle_length
        holder_radius = self.profile.nozzle_holder_radius

        if current_z is not None:
            early_out = holder_ends[:, 2] - holder_radius > current_z
        else:
            early_out = np.zeros(count, dtype=bool)

        query_idx = np.nonzero(~early_out)[0]
        if query_idx.size == 0:
            return collisions

        if current_z is not None:
            printed_bvh = self._get_printed_bvh(current_z)
            if printed_bvh is None:
                return collisions
        else:
            printed_bvh = self.part_bvh

        distances = printed_bvh.query_distance(holder_ends[query_idx])
        collisions[query_idx] = distances < holder_radius
        return collisions

    def batch_check_poses_with_bvh(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        printed_bvh: MeshBVH,
    ) -> np.ndarray:
        """Batch check poses against a custom printed-material BVH.

        No current_z filtering is applied; the caller is responsible for
        ensuring printed_bvh represents exactly the material that is already
        printed at the time of the check. Returns a bool array (True = collision).
        """
        points = np.asarray(points, dtype=float)
        normals = np.asarray(normals, dtype=float)
        if points.ndim != 2 or points.shape[1] != 3:
            raise ValueError(
                f"batch_check_poses_with_bvh: points must have shape (N, 3), got {points.shape}"
            )
        if normals.shape != points.shape:
            raise ValueError(
                f"batch_check_poses_with_bvh: normals must match points shape {points.shape}, "
                f"got {normals.shape}"
            )
        count = points.shape[0]
        collisions = np.zeros(count, dtype=bool)
        if count == 0:
            return collisions

        holder_ends = points + normals * self.profile.nozzle_length
        holder_radius = self.profile.nozzle_holder_radius

        distances = printed_bvh.query_distance(holder_ends)
        collisions = distances < holder_radius
        return collisions

    def query_closest_point(
        self,
        point: np.ndarray,
        current_z: Optional[float] = None,
    ) -> Tuple[Optional[np.ndarray], float]:
        """Return (closest_surface_point, distance) for a single point.

        Uses the printed-material BVH (clipped at current_z if given).
        Returns (None, inf) when there is no printed material.
        """
        if current_z is not None:
            printed_bvh = self._get_printed_bvh(current_z)
            if printed_bvh is None:
                return None, float("inf")
        else:
            printed_bvh = self.part_bvh

        p = np.asarray(point, dtype=float).reshape(1, 3)
        closest_points, distances, _ = printed_bvh.mesh.nearest.on_surface(p)
        return closest_points[0], float(distances[0])

    def sweep_check_path(self, path: FeaturePath, current_z: Optional[float] = None) -> List[CollisionReport]:
        reports = []
        for i, pt in enumerate(path.points):
            x, y, z = pt
            nx, ny, nz = path.normals[i]
            collision = self.validate_pose(x, y, z, nx, ny, nz, current_z=current_z)
            if collision:
                reports.append(CollisionReport(
                    path_id=path.path_id,
                    layer_idx=path.layer_idx,
                    point_index=i,
                    clearance=-1.0,
                    limiting_surface=collision,
                    suggested_remedy="Change orientation or limit amplitude."
                ))
                break
        return reports
