import numpy as np
import struct
import hashlib
from typing import Tuple, Dict, Any
from mesh_validator import validate_mesh_envelope

# A structured NumPy dtype corresponding to the binary STL 50-byte facet.
# normal (3 float32), v0 (3 float32), v1 (3 float32), v2 (3 float32), attr (uint16)
STL_DTYPE = np.dtype([
    ('normals', np.float32, (3,)),
    ('v0', np.float32, (3,)),
    ('v1', np.float32, (3,)),
    ('v2', np.float32, (3,)),
    ('attr', np.uint16, (1,))
])

class STLParseError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

def parse_binary_stl(file_path: str) -> Dict[str, Any]:
    """
    Parses a binary STL file into numpy arrays for vertices, faces, and normals.
    Computes a SHA-256 hash of the exact file bytes.
    Calculates fallback normals for invalid (zero or NaN) normal vectors.
    """
    # 1. Validate envelope to ensure safe reading
    # This will raise MeshEnvelopeError if invalid
    validate_mesh_envelope(file_path)

    # 2. Read entire file into memory (since F-021 limits size)
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    # 3. Hash calculation
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # 4. Extract metadata
    header = file_bytes[:80]
    count_bytes = file_bytes[80:84]
    triangle_count = struct.unpack("<I", count_bytes)[0]

    if triangle_count == 0:
        raise STLParseError("EMPTY_MESH", "The STL file contains zero triangles.")

    # 5. Fast slice the 50-byte record payload
    # Offset 84 bytes for the header + count
    payload = file_bytes[84: 84 + (triangle_count * 50)]
    
    # Parse records via C-optimized numpy buffers
    mesh_data = np.frombuffer(payload, dtype=STL_DTYPE)

    # 6. Extract raw geometry
    normals = mesh_data['normals'].copy()
    
    # Flatten the v0, v1, v2 into a continuous vertex array of shape (triangle_count * 3, 3)
    # Then we will return faces as sequential indexing since STL doesn't deduplicate vertices internally.
    vertices = np.empty((triangle_count * 3, 3), dtype=np.float32)
    vertices[0::3] = mesh_data['v0']
    vertices[1::3] = mesh_data['v1']
    vertices[2::3] = mesh_data['v2']
    
    # Faces are just continuous indices: [[0, 1, 2], [3, 4, 5], ...]
    faces = np.arange(triangle_count * 3, dtype=np.int32).reshape(-1, 3)

    # 7. Normal Fallback Calculations
    # Identify normals that are [0, 0, 0] or contain NaNs
    norm_magnitudes = np.linalg.norm(normals, axis=1)
    invalid_mask = (norm_magnitudes < 1e-6) | np.isnan(norm_magnitudes)
    
    if np.any(invalid_mask):
        # We need to recalculate normals for invalid indices using cross product
        # N = cross(v1 - v0, v2 - v0)
        v0_invalid = mesh_data['v0'][invalid_mask]
        v1_invalid = mesh_data['v1'][invalid_mask]
        v2_invalid = mesh_data['v2'][invalid_mask]
        
        cross_prod = np.cross(v1_invalid - v0_invalid, v2_invalid - v0_invalid)
        
        # Normalize the cross product
        cross_norms = np.linalg.norm(cross_prod, axis=1, keepdims=True)
        # Avoid division by zero if the triangle itself is degenerate (handled fully in F-023)
        safe_cross_norms = np.where(cross_norms < 1e-8, 1.0, cross_norms)
        
        fallback_normals = cross_prod / safe_cross_norms
        
        normals[invalid_mask] = fallback_normals

    # Ensure all normals are strictly normalized (some CAD tools output non-unit normals)
    final_magnitudes = np.linalg.norm(normals, axis=1, keepdims=True)
    safe_final = np.where(final_magnitudes < 1e-8, 1.0, final_magnitudes)
    normals = normals / safe_final

    return {
        "vertices": vertices,
        "faces": faces,
        "normals": normals,
        "content_hash": sha256_hash,
        "triangle_count": triangle_count,
        "header": header
    }
