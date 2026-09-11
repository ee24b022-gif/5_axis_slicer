import pytest
import struct
import os
from pathlib import Path

from mesh_validator import validate_mesh_envelope, MeshEnvelopeError, DEFAULT_MAX_FILE_SIZE

def create_binary_stl(path: Path, triangle_count: int, padding_bytes: int = 0):
    # 80 byte header
    header = b"Open5x Slicer Test STL File".ljust(80, b"\0")
    # 4 byte triangle count
    count = struct.pack("<I", triangle_count)
    
    # Write to file
    with open(path, "wb") as f:
        f.write(header)
        f.write(count)
        
        # 50 bytes per triangle
        # normal (3x4), vertex1 (3x4), vertex2 (3x4), vertex3 (3x4), attribute (2)
        triangle = (b"\0" * 48) + b"\0\0"
        for _ in range(triangle_count):
            f.write(triangle)
            
        if padding_bytes > 0:
            f.write(b"\0" * padding_bytes)

def test_valid_binary_stl(tmp_path: Path):
    valid_stl = tmp_path / "valid.stl"
    create_binary_stl(valid_stl, triangle_count=10)
    
    # Should not raise any exception
    validate_mesh_envelope(str(valid_stl))

def test_ascii_stl_rejected(tmp_path: Path):
    ascii_stl = tmp_path / "ascii.stl"
    with open(ascii_stl, "wb") as f:
        # Pad it to be large enough to pass the size check (>84 bytes)
        content = b"solid my_test_model\n" + b"  facet normal 0 0 0\n" * 10
        f.write(content)
        
    with pytest.raises(MeshEnvelopeError) as exc_info:
        validate_mesh_envelope(str(ascii_stl))
        
    assert exc_info.value.code == "ASCII_STL_NOT_SUPPORTED"

def test_file_too_small(tmp_path: Path):
    too_small = tmp_path / "small.stl"
    with open(too_small, "wb") as f:
        f.write(b"too small")
        
    with pytest.raises(MeshEnvelopeError) as exc_info:
        validate_mesh_envelope(str(too_small))
        
    assert exc_info.value.code == "FILE_TOO_SMALL"

def test_file_oversized(tmp_path: Path):
    oversized = tmp_path / "oversized.stl"
    # Just need it to be 84 bytes minimum for structure, but checking limits natively happens first by filesize.
    # We will write a dummy file exceeding the limit.
    limit = 100
    with open(oversized, "wb") as f:
        f.write(b"\0" * (limit + 1))
        
    with pytest.raises(MeshEnvelopeError) as exc_info:
        validate_mesh_envelope(str(oversized), max_size_bytes=limit)
        
    assert exc_info.value.code == "FILE_OVERSIZED"

def test_file_truncated_triangles(tmp_path: Path):
    truncated = tmp_path / "truncated.stl"
    
    header = b"\0" * 80
    # Say we have 10 triangles (needs 500 bytes)
    count = struct.pack("<I", 10)
    
    with open(truncated, "wb") as f:
        f.write(header)
        f.write(count)
        # But only provide 20 bytes!
        f.write(b"\0" * 20)
        
    with pytest.raises(MeshEnvelopeError) as exc_info:
        validate_mesh_envelope(str(truncated))
        
    assert exc_info.value.code == "FILE_TRUNCATED"

def test_file_padding_detected(tmp_path: Path):
    padded = tmp_path / "padded.stl"
    create_binary_stl(padded, triangle_count=2, padding_bytes=5)
    
    with pytest.raises(MeshEnvelopeError) as exc_info:
        validate_mesh_envelope(str(padded))
        
    assert exc_info.value.code == "FILE_PADDING_DETECTED"
