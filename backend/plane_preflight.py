import numpy as np
import trimesh
from typing import List, Optional
import math

from slice_plane_model import SlicePlane
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
from validation_model import ValidationDiagnostic

def compute_plane_intersection_z_min(mesh: trimesh.Trimesh, plane: SlicePlane) -> Optional[float]:
    """
    Computes the minimum global Z coordinate of any point where the slice plane intersects the mesh edges.
    Returns None if there is no intersection.
    """
    # 1. Compute signed distance of every vertex to the plane
    v = mesh.vertices
    o = np.array(plane.plane_origin)
    n = np.array(plane.unit_normal)
    
    # distance = (v - o) dot n
    d = np.dot(v - o, n)
    
    # 2. Check if there is an intersection at all
    d_max = np.max(d)
    d_min = np.min(d)
    
    if d_max < -1e-5 or d_min > 1e-5:
        return None # No intersection
        
    # 3. Find intersecting edges
    edges = mesh.edges_unique
    d_edges = d[edges]
    
    cross_mask = (d_edges[:, 0] * d_edges[:, 1]) <= 0.0
    crossing_edges = edges[cross_mask]
    
    if len(crossing_edges) == 0:
        return None
        
    # 4. Compute the actual 3D intersection points for the crossing edges
    v0 = v[crossing_edges[:, 0]]
    v1 = v[crossing_edges[:, 1]]
    
    d0 = d[crossing_edges[:, 0]]
    d1 = d[crossing_edges[:, 1]]
    
    # Protect against divide-by-zero if edge is perfectly on the plane
    denom = d0 - d1
    denom = np.where(np.abs(denom) < 1e-12, 1e-12, denom)
    
    t = d0 / denom
    
    # We only care about Z coordinate for the 12mm heuristic
    z0 = v0[:, 2]
    z1 = v1[:, 2]
    
    z_intersect = z0 + t * (z1 - z0)
    
    return np.min(z_intersect)


def preflight_slice_plane(mesh: trimesh.Trimesh, plane: SlicePlane) -> List[ValidationDiagnostic]:
    """
    Validates a noninitial slice plane before heavy computation.
    - Rejects planes that are purely horizontal (theta=0).
    - Rejects planes that completely miss the mesh.
    - Warns on planes that trigger the 12 mm bed/nozzle clearance heuristic.
    """
    diagnostics = []
    
    # Check for theta-zero (purely vertical normal)
    nx, ny, nz = plane.unit_normal
    if math.isclose(nx, 0.0, abs_tol=1e-7) and math.isclose(ny, 0.0, abs_tol=1e-7):
        diagnostics.append(ValidationDiagnostic(
            stage=JobStage.SECTIONING,
            severity=DiagnosticSeverity.ERROR,
            status=DiagnosticStatus.FAIL,
            code="INVALID_PLANE_THETA_ZERO",
            message="Noninitial slice planes cannot have a tilt angle of exactly zero (theta=0).",
            details={"normal": plane.unit_normal}
        ))
        return diagnostics
    
    # Run intersection and Z-height computation
    min_z = compute_plane_intersection_z_min(mesh, plane)
    
    if min_z is None:
        # Plane misses the mesh completely
        diagnostics.append(ValidationDiagnostic(
            stage=JobStage.SECTIONING,
            severity=DiagnosticSeverity.ERROR,
            status=DiagnosticStatus.FAIL,
            code="NONINTERSECTING_PLANE",
            message="The requested slicing plane does not intersect the mesh geometry.",
            details={"plane_origin": plane.plane_origin, "plane_normal": plane.unit_normal}
        ))
        return diagnostics
        
    # Plane intersects the mesh. Evaluate the 12 mm heuristic.
    HEURISTIC_LIMIT = 12.0
    
    if min_z < HEURISTIC_LIMIT:
        diagnostics.append(ValidationDiagnostic(
            stage=JobStage.SECTIONING,
            severity=DiagnosticSeverity.WARNING,
            status=DiagnosticStatus.WARNING,
            code="INSUFFICIENT_CLEARANCE",
            message=f"Slice plane intersection drops to Z={min_z:.2f}mm, violating the 12mm bed/nozzle clearance heuristic.",
            details={"min_intersection_z": float(min_z), "heuristic_limit": HEURISTIC_LIMIT, "formula": "min(section_points.z) >= 12.0"}
        ))
        
    return diagnostics
