import trimesh
import numpy as np
import manifold3d
from typing import List, Optional, Tuple
from slice_plane_model import SlicePlane

from typing import Tuple as _Tuple
from models import Diagnostic
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus


def _trimesh_to_manifold(mesh: trimesh.Trimesh) -> manifold3d.Manifold:
    """Convert a trimesh Trimesh to a manifold3d Manifold."""
    m_mesh = manifold3d.Mesh(
        np.ascontiguousarray(mesh.vertices, dtype=np.float32),
        np.ascontiguousarray(mesh.faces, dtype=np.uint32),
    )
    return manifold3d.Manifold(m_mesh)


def _manifold_to_trimesh(m: manifold3d.Manifold) -> trimesh.Trimesh:
    """Convert a manifold3d Manifold to a watertight trimesh Trimesh."""
    mesh_out = m.to_mesh()
    verts = np.asarray(mesh_out.vert_properties, dtype=np.float64)
    faces = np.asarray(mesh_out.tri_verts, dtype=np.int64)
    tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    tm.remove_unreferenced_vertices()
    return tm


def build_capped_chunks(mesh: trimesh.Trimesh, planes: List[SlicePlane]) -> List[Optional[trimesh.Trimesh]]:
    """
    Creates a capped mesh slice for each configured plane in deterministic order.

    The first element (Chunk 0) is the initial unaltered mesh geometry.
    Subsequent elements (Chunk 1..N) represent the portion of the mesh on the
    positive normal side of each successive slice plane, fully triangulated and capped.
    Each chunk is an independent slice from the ORIGINAL mesh (chunks may overlap);
    subtract_later_chunks() removes overlaps.

    Uses manifold3d trim_by_plane for watertight, volume-conserving splits.

    If a plane does not intersect the mesh (or the result is completely empty),
    the corresponding list entry will be explicitly None.

    Returns exactly 1 + len(planes) elements.
    """
    chunks: List[Optional[trimesh.Trimesh]] = []

    # Chunk 0: The base mesh (whole geometry)
    chunks.append(mesh.copy())

    if not planes:
        return chunks

    m = _trimesh_to_manifold(mesh)

    # Chunks 1..N: Independent positive-side slices from the original mesh
    for plane in planes:
        origin = np.asarray(plane.plane_origin, dtype=float)
        normal = np.asarray(plane.unit_normal, dtype=float)
        # Plane equation: normal · (X - origin) = 0  =>  normal · X = normal · origin
        offset = float(np.dot(normal, origin))

        # Positive side of plane: trim_by_plane returns the part in the direction
        # of `normal` from the plane, i.e. where normal·X > offset.
        chunk_m = m.trim_by_plane(normal, offset)

        if chunk_m.is_empty():
            chunks.append(None)
        else:
            chunk_tm = _manifold_to_trimesh(chunk_m)
            if chunk_tm.is_empty or len(chunk_tm.faces) == 0:
                chunks.append(None)
            else:
                chunks.append(chunk_tm)

    return chunks


def subtract_later_chunks(job_id: str, chunks: List[Optional[trimesh.Trimesh]]) -> _Tuple[List[Optional[trimesh.Trimesh]], List[Diagnostic]]:
    """
    Subtracts all later valid chunks from each earlier chunk to prevent geometric overlaps.
    Uses manifold3d boolean difference for robust, watertight results.

    Returns the modified chunks and a list of diagnostics for empty or invalid results.
    """
    diagnostics = []

    # Convert all valid chunks to manifold once
    manifolds: List[Optional[manifold3d.Manifold]] = []
    for c in chunks:
        if c is None or c.is_empty:
            manifolds.append(None)
        else:
            try:
                manifolds.append(_trimesh_to_manifold(c))
            except Exception:
                manifolds.append(None)

    for i in range(len(manifolds) - 1):
        if manifolds[i] is None or manifolds[i].is_empty():
            continue

        current = manifolds[i]

        for j in range(i + 1, len(manifolds)):
            if manifolds[j] is None or manifolds[j].is_empty():
                continue

            try:
                current = current - manifolds[j]
            except Exception as e:
                diagnostics.append(Diagnostic(
                    job_id=job_id,
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.ERROR,
                    status=DiagnosticStatus.FAIL,
                    code="BOOLEAN_SUBTRACTION_ERROR",
                    message=f"Boolean engine crashed when subtracting Chunk {j} from Chunk {i}: {str(e)}",
                    details={"chunk_i": i, "chunk_j": j}
                ))
                current = None
                break

            if current is None or current.is_empty():
                diagnostics.append(Diagnostic(
                    job_id=job_id,
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.WARNING,
                    status=DiagnosticStatus.WARNING,
                    code="EMPTY_CHUNK_AFTER_SUBTRACTION",
                    message=f"Chunk {i} became completely empty after subtracting Chunk {j}.",
                    details={"chunk_i": i, "chunk_j": j}
                ))
                current = None
                break

        if current is not None and not current.is_empty():
            try:
                chunks[i] = _manifold_to_trimesh(current)
                if chunks[i] is None or chunks[i].is_empty or len(chunks[i].faces) == 0:
                    chunks[i] = None
                    diagnostics.append(Diagnostic(
                        job_id=job_id,
                        stage=JobStage.SECTIONING,
                        severity=DiagnosticSeverity.WARNING,
                        status=DiagnosticStatus.WARNING,
                        code="EMPTY_CHUNK_AFTER_SUBTRACTION",
                        message=f"Chunk {i} produced no triangles after subtraction.",
                        details={"chunk_i": i}
                    ))
            except Exception as e:
                chunks[i] = None
                diagnostics.append(Diagnostic(
                    job_id=job_id,
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.ERROR,
                    status=DiagnosticStatus.FAIL,
                    code="BOOLEAN_SUBTRACTION_ERROR",
                    message=f"Failed to convert Chunk {i} back to trimesh after subtraction: {str(e)}",
                    details={"chunk_i": i}
                ))
        else:
            chunks[i] = None

    return chunks, diagnostics
