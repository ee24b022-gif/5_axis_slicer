import pytest
import io
import trimesh
import numpy as np
from pathlib import Path

from stl_parser import parse_binary_stl, STLParseError
from mesh_structural_validator import validate_mesh_structure
from transform_utils import apply_canonical_transform
from slice_intersection import slice_mesh_at_z
from polygonization import reconstruct_polygons
from shell_offset import generate_shells
from infill_generator import generate_line_infill
from shapely.geometry import Polygon
from brim_generator import generate_brim
from chunk_builder import build_capped_chunks
from chunk_slicer import slice_chunk

def test_binary_stl_parsing(tmp_path: Path):
    # 1. Binary STL
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    file_path = tmp_path / "valid.stl"
    mesh.export(file_path, file_type='stl')
    
    parsed_dict = parse_binary_stl(str(file_path))
    assert parsed_dict is not None
    assert parsed_dict["triangle_count"] == 12

def test_truncated_input(tmp_path: Path):
    # 2. Truncated Input
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    file_path = tmp_path / "truncated.stl"
    mesh.export(file_path, file_type='stl')
    
    # Truncate by 50 bytes (which cuts into the middle of face data)
    with open(file_path, 'rb') as f:
        data = f.read()
    with open(file_path, 'wb') as f:
        f.write(data[:-50])
    
    with pytest.raises(Exception):
        parse_binary_stl(str(file_path))

def test_vertices_on_plane():
    # 3. Vertices-on-Plane & Sections
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    # Box is centered at 0,0,0. Z goes from -5 to 5. Let's shift it to 0 to 10.
    mesh.apply_translation([0, 0, 5])
    
    # Slice exactly at Z=10.0 (top face exactly).
    segments = slice_mesh_at_z(mesh, 10.0)
    # The slicer will likely return empty since it's just a face. We just want to ensure it doesn't crash.
    assert isinstance(segments, np.ndarray)

    # Let's slice at Z=5.0 (midway)
    segments_mid = slice_mesh_at_z(mesh, 5.0)
    # Should be 4 segments for a square cross section (a simple 10x10 box has 2 triangles per face)
    # So the slice might have 4 segments.
    assert len(segments_mid) >= 4

def test_holes_and_multipolygons():
    # 4. Holes
    torus = trimesh.creation.torus(major_radius=10, minor_radius=3)
    # Torus is centered at origin. Slice at Z=0
    segments = slice_mesh_at_z(torus, 0.0)
    polygons = reconstruct_polygons(segments)
    
    # At Z=0, the torus cross section is two concentric circles.
    assert len(polygons.geoms) == 1
    assert len(polygons.geoms[0].interiors) == 1

    # 5. MultiPolygons
    # Two disjoint boxes
    box1 = trimesh.creation.box(extents=(5, 5, 5))
    box1.apply_translation([-10, 0, 0])
    box2 = trimesh.creation.box(extents=(5, 5, 5))
    box2.apply_translation([10, 0, 0])
    
    combined = trimesh.util.concatenate([box1, box2])
    segments_multi = slice_mesh_at_z(combined, 0.0)
    polygons_multi = reconstruct_polygons(segments_multi)
    
    # Should get 2 distinct polygons
    assert len(polygons_multi.geoms) == 2

def test_invalid_geometry():
    # 6. Invalid Geometry - Degenerate (Zero area face)
    vertices = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [2, 0, 0], # Collinear
        [0, 1, 0]
    ])
    faces = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]])
    degenerate_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    assert mesh is None or any("degenerate" in d["message"].lower() or "area" in d["message"].lower() for d in diagnostics)

    # Non-Manifold (Open mesh)
    vertices = np.array([[0,0,0], [1,0,0], [0,1,0]])
    faces = np.array([[0, 1, 2]])
    open_mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    assert mesh is None or any("watertight" in d["message"].lower() for d in diagnostics)

def test_shells_infill_brim():
    # 7. Shells, Infill, Brim
    box = trimesh.creation.box(extents=(20, 20, 20))
    segments = slice_mesh_at_z(box, 0.0)
    polygons = reconstruct_polygons(segments)
    poly = polygons.geoms[0]
    
    # Shells
    shells = generate_shells(poly, shell_count=3, line_width=0.4)
    # 3 shells generated
    assert len(shells) == 3
    
    # Infill
    # The innermost shell is shells[-1] which is a LinearRing. We need a Polygon.
    infill_lines = generate_line_infill(Polygon(shells[-1]), spacing=5.0, angle_degrees=45)
    assert len(infill_lines) > 0
    
    # Brim
    brim_lines_list = generate_brim(poly, line_width=0.4, brim_lines=5)
    assert len(brim_lines_list) == 5

def test_chunks_and_transforms():
    # 8. Chunks
    tall_box = trimesh.creation.box(extents=(10, 10, 40))
    tall_box.apply_translation([0, 0, 20]) # Z from 0 to 40
    
    chunks = build_capped_chunks(tall_box, [])
    # A single chunk for 3-axis
    assert len(chunks) == 1
    
    sliced = slice_chunk(
        mesh=tall_box, 
        chunk_idx=0, 
        transform_matrix=np.eye(4).flatten().tolist(), 
        z_min=0.0, 
        z_max=40.0, 
        layer_height=0.2
    )
    # 40 / 0.2 = 200 layers
    assert len(sliced) == 200

    # 9. Transforms
    mesh, mat = apply_canonical_transform(tall_box, scale=2.0, rot_x_deg=90)
    # Scale 2.0 -> extents become 20, 20, 80
    # Rot X 90 -> extents become 20, 80, 20
    assert np.isclose(mesh.bounds[1][0] - mesh.bounds[0][0], 20)
    assert np.isclose(mesh.bounds[1][1] - mesh.bounds[0][1], 80)
    assert np.isclose(mesh.bounds[1][2] - mesh.bounds[0][2], 20)
    
    # Ensure min Z is 0
    assert np.isclose(mesh.bounds[0][2], 0)
