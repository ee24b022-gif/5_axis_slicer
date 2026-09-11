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
