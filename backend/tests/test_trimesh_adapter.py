import pytest
import numpy as np
import trimesh
from trimesh_adapter import slice_mesh_multiplane

def test_trimesh_multiplane_basic():
    # Box from [-1, -1, -1] to [1, 1, 1]
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    origin = np.array([0.0, 0.0, -1.0])
    normal = np.array([0.0, 0.0, 1.0])
    
    # 3 slices: exactly at Z=-0.5, Z=0.0, Z=0.5
    heights = [0.5, 1.0, 1.5]
    
    lines, to_3D, face_index = slice_mesh_multiplane(mesh, origin, normal, heights)
    
    assert len(lines) == 3
    assert len(to_3D) == 3
    assert len(face_index) == 3
    
    # Each horizontal slice of a box has 8 segments (2 per face)
    for l in lines:
        assert l.shape[0] == 8
        assert l.shape[1] == 2
        assert l.shape[2] == 2

def test_trimesh_multiplane_transforms():
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    origin = np.array([0.0, 0.0, -1.0])
    normal = np.array([0.0, 0.0, 1.0])
    heights = [1.0] # Cuts at Z=0.0
    
    lines, to_3D, _ = slice_mesh_multiplane(mesh, origin, normal, heights)
    
    T = to_3D[0]
    # The transform should translate 2D points into Z=0.0 plane
    
    # Take the first segment's first point
    pt_2d = lines[0][0][0]
    
    # Apply homogeneous transform
    pt_3d_hom = T @ np.array([pt_2d[0], pt_2d[1], 0.0, 1.0])
    pt_3d = pt_3d_hom[:3] / pt_3d_hom[3]
    
    # The Z height should be exactly 0.0 (which is origin + height)
    assert np.isclose(pt_3d[2], 0.0)
    
    # Testing another height
    heights2 = [1.5] # Cuts at Z=0.5
    lines2, to_3D2, _ = slice_mesh_multiplane(mesh, origin, normal, heights2)
    T2 = to_3D2[0]
    pt_2d_2 = lines2[0][0][0]
    pt_3d_hom2 = T2 @ np.array([pt_2d_2[0], pt_2d_2[1], 0.0, 1.0])
    pt_3d2 = pt_3d_hom2[:3] / pt_3d_hom2[3]
    assert np.isclose(pt_3d2[2], 0.5)

def test_trimesh_multiplane_empty():
    mesh = trimesh.creation.box(extents=(2, 2, 2))
    origin = np.array([0.0, 0.0, 0.0])
    normal = np.array([0.0, 0.0, 1.0])
    
    # Heights completely above and below the mesh
    heights = [-5.0, 5.0]
    
    lines, to_3D, face_index = slice_mesh_multiplane(mesh, origin, normal, heights)
    
    assert len(lines) == 2
    # They should be empty arrays
    for l in lines:
        assert len(l) == 0
        
    for f in face_index:
        assert len(f) == 0
