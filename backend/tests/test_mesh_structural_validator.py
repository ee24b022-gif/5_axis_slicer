import pytest
import numpy as np
import trimesh

from enums import DiagnosticSeverity
from mesh_structural_validator import (
    validate_mesh_structure, 
    MAX_TRIANGLE_COUNT, 
    MAX_COORDINATE_VALUE
)

def create_valid_cube():
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    # Return unmerged raw lists mimicking naive STL parsed buffers
    return mesh.vertices[mesh.faces].reshape(-1, 3), np.arange(len(mesh.faces) * 3).reshape(-1, 3)

def test_valid_geometry():
    vertices, faces = create_valid_cube()
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    
    assert mesh is not None
    # Watertight, non-degenerate boxes have no structural issues
    assert len(diagnostics) == 0

def test_excessive_triangles():
    # Construct a dummy array that exceeds the limit
    excess = MAX_TRIANGLE_COUNT + 1
    # We don't actually need to allocate massive arrays, just the faces length matters for the check
    dummy_faces = np.zeros((excess, 3), dtype=np.int32)
    dummy_vertices = np.zeros((0, 3), dtype=np.float32)
    
    mesh, diagnostics = validate_mesh_structure(dummy_vertices, dummy_faces)
    
    assert mesh is None
    assert len(diagnostics) == 1
    assert diagnostics[0]["severity"] == DiagnosticSeverity.ERROR
    assert diagnostics[0]["code"] == "EXCESSIVE_TRIANGLES"

def test_out_of_bounds_geometry():
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [MAX_COORDINATE_VALUE + 10.0, 0.0, 0.0],
        [0.0, 1.0, 0.0]
    ], dtype=np.float32)
    faces = np.array([[0, 1, 2]], dtype=np.int32)
    
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    
    assert mesh is None
    assert len(diagnostics) == 1
    assert diagnostics[0]["severity"] == DiagnosticSeverity.ERROR
    assert diagnostics[0]["code"] == "OUT_OF_BOUNDS"

def test_degenerate_face_removal():
    # A triangle where two vertices are identical has zero area
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        # Add a valid triangle to prevent EMPTY_GEOMETRY error
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0]
    ], dtype=np.float32)
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int32)
    
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    
    # Check for DEGENERATE_FACES_REMOVED
    codes = [d["code"] for d in diagnostics]
    assert "DEGENERATE_FACES_REMOVED" in codes
    assert mesh is not None
    assert len(mesh.faces) == 1

def test_open_geometry():
    vertices, faces = create_valid_cube()
    # Remove one face to make it open (not watertight)
    open_faces = faces[:-1]
    
    mesh, diagnostics = validate_mesh_structure(vertices, open_faces)
    
    codes = [d["code"] for d in diagnostics]
    assert "OPEN_GEOMETRY" in codes
    
    # It should still be parsed and returned!
    assert mesh is not None

def test_empty_geometry():
    # Only degenerate faces
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0]
    ], dtype=np.float32)
    faces = np.array([[0, 1, 2]], dtype=np.int32)
    
    mesh, diagnostics = validate_mesh_structure(vertices, faces)
    
    codes = [d["code"] for d in diagnostics]
    assert "EMPTY_GEOMETRY" in codes
    assert "DEGENERATE_FACES_REMOVED" in codes
