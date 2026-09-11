import numpy as np
import trimesh
from typing import List, Dict, Any, Tuple
from enums import DiagnosticSeverity

# Upper threshold to protect against memory exhaustion or integer overflow
MAX_TRIANGLE_COUNT = 5_000_000
# Absolute limits on spatial bounds (e.g. 50 meters, catching floating point garbage)
MAX_COORDINATE_VALUE = 50_000.0 

def validate_mesh_structure(vertices: np.ndarray, faces: np.ndarray) -> Tuple[trimesh.Trimesh, List[Dict[str, Any]]]:
    """
    Validates structural mesh geometry natively through trimesh properties.
    Returns the initialized Trimesh object and a list of diagnostics.
    """
    diagnostics = []

    # 1. Count checks
    if len(faces) > MAX_TRIANGLE_COUNT:
        diagnostics.append({
            "severity": DiagnosticSeverity.ERROR,
            "code": "EXCESSIVE_TRIANGLES",
            "message": f"Mesh contains {len(faces)} triangles, exceeding the {MAX_TRIANGLE_COUNT} limit."
        })
        # Fast fail return before allocating Trimesh overhead on extreme meshes
        return None, diagnostics

    # 2. Coordinate range checks
    if len(vertices) > 0:
        min_bounds = np.min(vertices, axis=0)
        max_bounds = np.max(vertices, axis=0)
        
        if np.any(min_bounds < -MAX_COORDINATE_VALUE) or np.any(max_bounds > MAX_COORDINATE_VALUE):
            diagnostics.append({
                "severity": DiagnosticSeverity.ERROR,
                "code": "OUT_OF_BOUNDS",
                "message": f"Mesh coordinates exceed maximum supported spatial volume (+/- {MAX_COORDINATE_VALUE}mm)."
            })
            return None, diagnostics

    # 3. Trimesh allocation
    # process=True automatically merges vertices and removes degenerate zero-area faces.
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)

    # 4. Degenerate Geometry Check
    # Remove faces that reference the same vertex twice or have zero area.
    mesh.update_faces(mesh.nondegenerate_faces())
    
    # If the processed face count is less than the raw input, degenerates were removed.
    if len(mesh.faces) < len(faces):
        dropped = len(faces) - len(mesh.faces)
        diagnostics.append({
            "severity": DiagnosticSeverity.WARNING,
            "code": "DEGENERATE_FACES_REMOVED",
            "message": f"Mesh contained {dropped} zero-area degenerate faces that were automatically removed."
        })

    if len(mesh.faces) == 0:
        diagnostics.append({
            "severity": DiagnosticSeverity.ERROR,
            "code": "EMPTY_GEOMETRY",
            "message": "Mesh has no valid faces remaining after removing degenerates."
        })
        return mesh, diagnostics

    # 5. Non-Manifold / Watertight Checks
    if not mesh.is_watertight:
        diagnostics.append({
            "severity": DiagnosticSeverity.WARNING,
            "code": "OPEN_GEOMETRY",
            "message": "Mesh is not watertight (contains holes). Slicing artifacts may occur."
        })

    # Winding consistency and edge-manifoldness
    if not mesh.is_winding_consistent:
        diagnostics.append({
            "severity": DiagnosticSeverity.WARNING,
            "code": "INCONSISTENT_WINDING",
            "message": "Mesh has inconsistent face normals or non-manifold edges."
        })

    return mesh, diagnostics
