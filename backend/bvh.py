import trimesh
import numpy as np
from typing import Tuple, List

class MeshBVH:
    """
    Acceleration structure for spatial queries against the printed part.
    Delegates to trimesh's internal BVH/rtree for robustness.
    """
    def __init__(self, vertices: np.ndarray, faces: np.ndarray):
        self.mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        # Ensure the spatial index is built
        _ = self.mesh.bounds

    def query_distance(self, points: np.ndarray) -> np.ndarray:
        """
        Returns the signed/unsigned distance from each point in `points` to the nearest mesh surface.
        points: (N, 3)
        returns: (N,) distances
        """
        # trimesh closest point: returns closest_points, distances, triangle_ids
        _, distances, _ = self.mesh.nearest.on_surface(points)
        return distances

    def check_capsule_collision(self, p_start: np.ndarray, p_end: np.ndarray, radius: float) -> bool:
        """
        Checks if a capsule (cylinder with rounded caps) defined by segment p_start->p_end 
        and `radius` collides with the mesh.
        
        Since exact swept-volume capsule vs mesh is complex, we sample points along 
        the capsule axis and do a distance query.
        """
        length = np.linalg.norm(p_end - p_start)
        if length == 0:
            return self.query_distance(np.array([p_start]))[0] <= radius

        # Sample points along the segment (at least every radius/2 distance)
        num_samples = max(2, int(np.ceil(length / (radius / 2.0))))
        t = np.linspace(0, 1, num_samples)
        samples = p_start[None, :] + t[:, None] * (p_end - p_start)[None, :]
        
        distances = self.query_distance(samples)
        return np.any(distances <= radius)
        
    def get_mesh(self):
        return self.mesh
