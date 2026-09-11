import numpy as np
import trimesh

def slice_mesh_at_z(mesh: trimesh.Trimesh, z: float) -> np.ndarray:
    """
    Slices a mesh at a given z height using the half-open plane convention.
    Returns an array of line segments of shape (N, 2, 2) where N is the number of segments.
    """
    faces = mesh.faces
    vertices = mesh.vertices
    
    # M faces, each with 3 vertices, each with 3 coords
    triangles = vertices[faces] # shape (M, 3, 3)
    
    # Extract edges. For each triangle, 3 edges:
    # edge 0: vertex 0 -> 1
    # edge 1: vertex 1 -> 2
    # edge 2: vertex 2 -> 0
    
    v0 = triangles[:, 0, :]
    v1 = triangles[:, 1, :]
    v2 = triangles[:, 2, :]
    
    z0 = v0[:, 2]
    z1 = v1[:, 2]
    z2 = v2[:, 2]
    
    # Check intersections
    cross_01 = ((z0 < z) & (z <= z1)) | ((z1 < z) & (z <= z0))
    cross_12 = ((z1 < z) & (z <= z2)) | ((z2 < z) & (z <= z1))
    cross_20 = ((z2 < z) & (z <= z0)) | ((z0 < z) & (z <= z2))
    
    # Number of crossings for each face
    num_cross = cross_01.astype(int) + cross_12.astype(int) + cross_20.astype(int)
    
    # Valid faces must have exactly 2 crossings. 
    # (Tangential edges on the plane might be handled differently, but half-open guarantees exactly 0 or 2)
    valid_faces = num_cross == 2
    
    # We will build segment endpoints. We know each valid face has exactly two points.
    # To extract them easily, we can compute the intersection point for all edges and then filter.
    
    def get_intersection(v_start, v_end, cross_mask):
        dz = v_end[:, 2] - v_start[:, 2]
        # Avoid divide by zero
        dz = np.where(dz == 0, 1e-8, dz)
        t = (z - v_start[:, 2]) / dz
        # x, y only
        x = v_start[:, 0] + t * (v_end[:, 0] - v_start[:, 0])
        y = v_start[:, 1] + t * (v_end[:, 1] - v_start[:, 1])
        return np.column_stack((x, y))
        
    p01 = get_intersection(v0, v1, cross_01)
    p12 = get_intersection(v1, v2, cross_12)
    p20 = get_intersection(v2, v0, cross_20)
    
    # Now assemble the points for the valid faces
    p01_valid = cross_01[valid_faces]
    p12_valid = cross_12[valid_faces]
    p20_valid = cross_20[valid_faces]
    
    p01_pts = p01[valid_faces]
    p12_pts = p12[valid_faces]
    p20_pts = p20[valid_faces]
    
    # We need to construct shape (N, 2, 2)
    N = np.sum(valid_faces)
    segments = np.zeros((N, 2, 2))
    
    # For each face, find the first and second point
    # There are exactly 2 True in (p01_valid, p12_valid, p20_valid) for each row
    
    # Condition 01 and 12
    mask1 = p01_valid & p12_valid
    segments[mask1, 0] = p01_pts[mask1]
    segments[mask1, 1] = p12_pts[mask1]
    
    # Condition 12 and 20
    mask2 = p12_valid & p20_valid
    segments[mask2, 0] = p12_pts[mask2]
    segments[mask2, 1] = p20_pts[mask2]
    
    # Condition 20 and 01
    mask3 = p20_valid & p01_valid
    segments[mask3, 0] = p20_pts[mask3]
    segments[mask3, 1] = p01_pts[mask3]
    
    return segments

mesh = trimesh.creation.box(extents=(2, 2, 2))
# The box is from -1 to 1. Let's slice exactly at 1.0. Because of half-open, 
# z=1.0 might hit the top face. 
# Z is from -1 to 1.
# At z=0.0:
segs = slice_mesh_at_z(mesh, 0.0)
print(f"Segs at 0.0: {len(segs)}")
segs = slice_mesh_at_z(mesh, 1.0)
print(f"Segs at 1.0 (top): {len(segs)}")
segs = slice_mesh_at_z(mesh, -1.0)
print(f"Segs at -1.0 (bottom): {len(segs)}")

