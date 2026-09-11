import pytest
import numpy as np
import struct
import hashlib
from pathlib import Path

from stl_parser import parse_binary_stl, STLParseError
from mesh_validator import MeshEnvelopeError

def create_stl_fixture(path: Path, normals=None, v0=None, v1=None, v2=None):
    """
    Creates a single-triangle binary STL for testing.
    """
    triangle_count = 1
    
    # 80 byte header
    header = b"Parser Test STL File".ljust(80, b"\0")
    # 4 byte triangle count
    count = struct.pack("<I", triangle_count)
    
    # Defaults
    if normals is None:
        normals = [0.0, 0.0, 1.0] # UP
    if v0 is None:
        v0 = [0.0, 0.0, 0.0]
    if v1 is None:
        v1 = [1.0, 0.0, 0.0]
    if v2 is None:
        v2 = [0.0, 1.0, 0.0]
        
    triangle_bytes = struct.pack(
        "<12fH",
        *normals,
        *v0,
        *v1,
        *v2,
        0 # attribute
    )
    
    content = header + count + triangle_bytes
    with open(path, "wb") as f:
        f.write(content)
        
    return content

def test_parse_valid_binary_stl(tmp_path: Path):
    stl_path = tmp_path / "valid.stl"
    expected_content = create_stl_fixture(stl_path)
    
    result = parse_binary_stl(str(stl_path))
    
    assert result["triangle_count"] == 1
    assert result["vertices"].shape == (3, 3)
    assert result["faces"].shape == (1, 3)
    assert result["normals"].shape == (1, 3)
    
    # Vertices flattened check
    np.testing.assert_almost_equal(result["vertices"][0], [0.0, 0.0, 0.0])
    np.testing.assert_almost_equal(result["vertices"][1], [1.0, 0.0, 0.0])
    np.testing.assert_almost_equal(result["vertices"][2], [0.0, 1.0, 0.0])
    
    # Hash check
    expected_hash = hashlib.sha256(expected_content).hexdigest()
    assert result["content_hash"] == expected_hash

def test_normal_fallback_behavior(tmp_path: Path):
    stl_path = tmp_path / "zero_normals.stl"
    # Pass explicit [0, 0, 0] normal
    create_stl_fixture(stl_path, normals=[0.0, 0.0, 0.0])
    
    result = parse_binary_stl(str(stl_path))
    
    # Normal should be recalculated using cross product (v1-v0 x v2-v0)
    # v1 = [1,0,0], v2 = [0,1,0]
    # cross = [0, 0, 1]
    np.testing.assert_almost_equal(result["normals"][0], [0.0, 0.0, 1.0])

def test_normal_normalization_fix(tmp_path: Path):
    stl_path = tmp_path / "unnormalized.stl"
    # Pass explicit non-unit normal [0, 0, 10]
    create_stl_fixture(stl_path, normals=[0.0, 0.0, 10.0])
    
    result = parse_binary_stl(str(stl_path))
    
    # Normal should be converted to unit vector [0, 0, 1]
    np.testing.assert_almost_equal(result["normals"][0], [0.0, 0.0, 1.0])

def test_empty_mesh_rejected(tmp_path: Path):
    stl_path = tmp_path / "empty.stl"
    
    header = b"Empty STL".ljust(80, b"\0")
    count = struct.pack("<I", 0)
    
    with open(stl_path, "wb") as f:
        f.write(header + count)
        
    with pytest.raises(STLParseError) as exc_info:
        parse_binary_stl(str(stl_path))
        
    assert exc_info.value.code == "EMPTY_MESH"

def test_hash_consistency_with_byte_changes(tmp_path: Path):
    path1 = tmp_path / "mesh1.stl"
    path2 = tmp_path / "mesh2.stl"
    
    # Same geometry, different header
    create_stl_fixture(path1)
    
    header2 = b"Different Header".ljust(80, b"\0")
    count2 = struct.pack("<I", 1)
    tri_bytes = struct.pack("<12fH", 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0)
    
    with open(path2, "wb") as f:
        f.write(header2 + count2 + tri_bytes)
        
    res1 = parse_binary_stl(str(path1))
    res2 = parse_binary_stl(str(path2))
    
    assert res1["content_hash"] != res2["content_hash"], "Different files must have different hashes"
    np.testing.assert_array_equal(res1["vertices"], res2["vertices"])
