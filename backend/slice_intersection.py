import numpy as np
import trimesh

def slice_mesh_at_z(mesh: trimesh.Trimesh, z: float) -> np.ndarray:
    """
    Slices a mesh at a given z height using the half-open plane convention.
    
    This function implements a deterministic horizontal triangle-edge intersection.
    An edge from vertex A to vertex B intersects the plane Z=z if and only if:
    (Z_a < z <= Z_b) or (Z_b < z <= Z_a).
    
    By strictly adhering to a half-open boundary interval, flat horizontal surfaces 
    and edges exactly intersecting the plane will consistently generate 0 or 2 
    unique points per face. This mathematically prevents duplicate intersection bugs.
    
    Args:
        mesh (trimesh.Trimesh): The validated trimesh object.
        z (float): The absolute Z height of the slicing plane.
        
    Returns:
        np.ndarray: Array of line segments of shape (N, 2, 2) where N is the number 
        of generated segments (x, y coordinates).
    """
    faces = mesh.faces
    vertices = mesh.vertices
    
    # Shape: (M, 3, 3) where M is number of faces
    triangles = vertices[faces]
    
    v0 = triangles[:, 0, :]
    v1 = triangles[:, 1, :]
    v2 = triangles[:, 2, :]
    
    z0 = v0[:, 2]
    z1 = v1[:, 2]
    z2 = v2[:, 2]
    
    # Half-open plane intersection checks for the 3 edges
    cross_01 = ((z0 < z) & (z <= z1)) | ((z1 < z) & (z <= z0))
    cross_12 = ((z1 < z) & (z <= z2)) | ((z2 < z) & (z <= z1))
    cross_20 = ((z2 < z) & (z <= z0)) | ((z0 < z) & (z <= z2))
    
    num_cross = cross_01.astype(int) + cross_12.astype(int) + cross_20.astype(int)
    
    # Faces crossing exactly twice are mathematically guaranteed 
    # to produce a valid segment across the plane.
    valid_faces = num_cross == 2
    
    # If no segments, return early
    if not np.any(valid_faces):
        return np.zeros((0, 2, 2))
    
    def get_intersection(v_start, v_end, cross_mask):
        dz = v_end[:, 2] - v_start[:, 2]
        # Protect against divide-by-zero on perfectly flat edges
        # (Though flat edges technically shouldn't cross under half-open unless dz is non-zero)
        dz = np.where(dz == 0, 1e-8, dz)
        t = (z - v_start[:, 2]) / dz
        x = v_start[:, 0] + t * (v_end[:, 0] - v_start[:, 0])
        y = v_start[:, 1] + t * (v_end[:, 1] - v_start[:, 1])
        return np.column_stack((x, y))
        
    p01 = get_intersection(v0, v1, cross_01)
    p12 = get_intersection(v1, v2, cross_12)
    p20 = get_intersection(v2, v0, cross_20)
    
    p01_valid = cross_01[valid_faces]
    p12_valid = cross_12[valid_faces]
    p20_valid = cross_20[valid_faces]
    
    p01_pts = p01[valid_faces]
    p12_pts = p12[valid_faces]
    p20_pts = p20[valid_faces]
    
    N = np.sum(valid_faces)
    segments = np.zeros((N, 2, 2))
    
    # Assemble exactly two endpoints per segment based on masks
    mask1 = p01_valid & p12_valid
    segments[mask1, 0] = p01_pts[mask1]
    segments[mask1, 1] = p12_pts[mask1]
    
    mask2 = p12_valid & p20_valid
    segments[mask2, 0] = p12_pts[mask2]
    segments[mask2, 1] = p20_pts[mask2]
    
    mask3 = p20_valid & p01_valid
    segments[mask3, 0] = p20_pts[mask3]
    segments[mask3, 1] = p01_pts[mask3]
    
    return segments
