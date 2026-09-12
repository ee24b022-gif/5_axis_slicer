import trimesh
import trimesh.transformations as tf
import numpy as np
from typing import Tuple

def apply_canonical_transform(
    mesh: trimesh.Trimesh, 
    scale: float = 1.0, 
    rot_x_deg: float = 0.0, 
    rot_y_deg: float = 0.0, 
    rot_z_deg: float = 0.0, 
    trans_x: float = 0.0, 
    trans_y: float = 0.0
) -> Tuple[trimesh.Trimesh, np.ndarray]:
    """
    Applies a deterministic transformation sequence to place a part canonically on the print bed.
    
    Sequence:
    1. Scale
    2. Rotations (Z, Y, X order mathematically, but typically X, Y, Z applied)
       We will apply euler rotation 'sxyz' (static X, Y, Z).
    3. Floor anchoring (Z min = 0) and X/Y centering
    4. Explicit user translations (trans_x, trans_y)
    
    Returns the updated mesh and the final 4x4 affine matrix applied.
    """
    if scale <= 0.0:
        raise ValueError(f"Scale must be strictly positive. Received: {scale}")

    # 1. Scale matrix
    # Creates a 4x4 matrix scaled uniformly
    scale_mat = tf.scale_matrix(scale)

    # 2. Rotation matrix
    rot_x = np.radians(rot_x_deg)
    rot_y = np.radians(rot_y_deg)
    rot_z = np.radians(rot_z_deg)
    # 'sxyz' means rotate around static X, then Y, then Z. 
    rot_mat = tf.euler_matrix(rot_x, rot_y, rot_z, axes='sxyz')

    # Combine scale and rotation to find the intermediate bounding box
    sr_mat = tf.concatenate_matrices(rot_mat, scale_mat)
    
    # We must apply this intermediate transform to compute the precise bounds
    # Because bounding box changes non-linearly under rotation.
    mesh.apply_transform(sr_mat)
    
    # Now find the bounds of the scaled and rotated mesh
    bounds = mesh.bounds
    min_z = bounds[0][2]
    center_x = mesh.centroid[0] if hasattr(mesh, 'centroid') and mesh.centroid is not None else (bounds[0][0] + bounds[1][0]) / 2.0
    center_y = mesh.centroid[1] if hasattr(mesh, 'centroid') and mesh.centroid is not None else (bounds[0][1] + bounds[1][1]) / 2.0
    
    # Actually, centering by bounding box center is more stable for slicers than centroid mass.
    bb_center_x = (bounds[0][0] + bounds[1][0]) / 2.0
    bb_center_y = (bounds[0][1] + bounds[1][1]) / 2.0

    # 3. Anchoring and Translation matrix
    # We want to shift X/Y such that its bounding box center is at (trans_x, trans_y)
    # We want to shift Z such that its min_z is at 0
    shift_x = trans_x - bb_center_x
    shift_y = trans_y - bb_center_y
    shift_z = -min_z
    
    trans_mat = tf.translation_matrix([shift_x, shift_y, shift_z])
    
    # Apply the translation
    mesh.apply_transform(trans_mat)
    
    # The final combined matrix applied mathematically from the original frame:
    # final_mat = trans_mat * sr_mat
    final_mat = tf.concatenate_matrices(trans_mat, sr_mat)
    
    return mesh, final_mat

from slice_plane_model import SlicePlane

def align_chunk_to_slice_plane(mesh: trimesh.Trimesh, plane: SlicePlane) -> Tuple[trimesh.Trimesh, list[float], float, float]:
    """
    Transforms a chunk from world space to a local slicing frame where:
    - The slicing plane becomes the XY plane (Z=0).
    - The mesh extends into +Z.
    
    Returns:
        - The transformed mesh (modified in-place, but returned for convenience)
        - The 16-element flat list representing the local_to_world 4x4 matrix (for Chunk ORM metadata)
        - min_z (which should mathematically be near 0.0)
        - max_z (the maximum height of the chunk)
    """
    # 1. Build local-to-world affine matrix
    local_to_world = np.eye(4, dtype=np.float64)
    local_to_world[0:3, 0] = plane.local_x
    local_to_world[0:3, 1] = plane.local_y
    local_to_world[0:3, 2] = plane.unit_normal
    local_to_world[0:3, 3] = plane.plane_origin
    
    # 2. Invert to get world-to-local transformation
    world_to_local = np.linalg.inv(local_to_world)
    
    # 3. Apply the transformation to the mesh
    mesh.apply_transform(world_to_local)
    
    # 4. Compute slicing bounds
    bounds = mesh.bounds
    min_z = float(bounds[0][2])
    max_z = float(bounds[1][2])
    
    flat_matrix = local_to_world.flatten().tolist()
    
    return mesh, flat_matrix, min_z, max_z

from typing import List

def restore_segments_to_world(segments: np.ndarray, z_height: float, transform_matrix: List[float]) -> np.ndarray:
    """
    Restores an (N, 2, 2) array of 2D line segments at a given z_height
    back to its (N, 2, 3) 3D world coordinates using the chunk's 4x4 matrix.
    """
    if segments.size == 0:
        return np.empty((0, 2, 3), dtype=np.float64)
        
    N = segments.shape[0]
    # segments shape is (N, 2, 2)
    
    # 1. Expand to (N, 2, 3) by appending z_height
    z_col = np.full((N, 2, 1), z_height, dtype=np.float64)
    pts_3d = np.concatenate([segments, z_col], axis=-1)  # Shape (N, 2, 3)
    
    # 2. Reshape to (N*2, 3) for matrix multiplication
    pts_3d_flat = pts_3d.reshape(-1, 3)
    
    # 3. Inflate to homogeneous coordinates (N*2, 4)
    ones = np.ones((pts_3d_flat.shape[0], 1), dtype=np.float64)
    pts_4d = np.concatenate([pts_3d_flat, ones], axis=-1)
    
    # 4. Transform
    mat = np.array(transform_matrix, dtype=np.float64).reshape(4, 4)
    pts_4d_transformed = (mat @ pts_4d.T).T
    
    # 5. Normalize and strip homogeneous
    pts_3d_transformed = pts_4d_transformed[:, 0:3] / pts_4d_transformed[:, 3:4]
    
    # 6. Reshape back to (N, 2, 3)
    return pts_3d_transformed.reshape(N, 2, 3)

