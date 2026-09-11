import trimesh
import numpy as np
from typing import Tuple, List, Optional

def slice_mesh_multiplane(
    mesh: trimesh.Trimesh, 
    plane_origin: np.ndarray, 
    plane_normal: np.ndarray, 
    heights: List[float]
) -> Tuple[List[np.ndarray], List[np.ndarray], List[np.ndarray]]:
    """
    Adapter isolating the `trimesh.intersections.mesh_multiplane` slicing engine.
    This provides an explicitly validated three-axis horizontal slicing reference.
    
    Args:
        mesh (trimesh.Trimesh): The target geometry.
        plane_origin (np.ndarray): The starting point of the slicing plane stack.
        plane_normal (np.ndarray): The parallel normal vector.
        heights (List[float]): Linear distance offsets along the normal.
        
    Returns:
        Tuple containing:
        - lines: List of M arrays of shape (N, 2, 2) holding 2D line segments per layer.
        - to_3D: List of M (4, 4) homogeneous transforms projecting 2D lines to 3D space.
        - face_index: List of M arrays of shape (N,) identifying the source face per segment.
    """
    # Defensive typing standardization
    origin = np.asarray(plane_origin, dtype=np.float64)
    normal = np.asarray(plane_normal, dtype=np.float64)
    heights = np.asarray(heights, dtype=np.float64)
    
    if mesh.is_empty:
        return [np.zeros((0, 2, 2))] * len(heights), [np.eye(4)] * len(heights), [np.zeros(0, dtype=int)] * len(heights)

    lines, to_3D, face_index = trimesh.intersections.mesh_multiplane(
        mesh=mesh,
        plane_origin=origin,
        plane_normal=normal,
        heights=heights
    )
    
    # mesh_multiplane returns empty arrays gracefully if out of bounds, but we ensure list format explicitly
    return lines, to_3D, face_index
