import trimesh
from typing import List, Optional
from slice_plane_model import SlicePlane

def build_capped_chunks(mesh: trimesh.Trimesh, planes: List[SlicePlane]) -> List[Optional[trimesh.Trimesh]]:
    """
    Creates a capped mesh slice for each configured plane in deterministic order.
    
    The first element (Chunk 0) is the initial unaltered mesh geometry.
    Subsequent elements (Chunk 1..N) represent the portion of the mesh on the
    positive side of each successive slice plane, fully triangulated and capped.
    
    If a plane does not intersect the mesh (or the result is completely empty),
    the corresponding list entry will be explicitly None.
    
    Returns exactly 1 + len(planes) elements.
    """
    chunks: List[Optional[trimesh.Trimesh]] = []
    
    # Chunk 0: The base mesh
    chunks.append(mesh.copy())
    
    # Chunks 1..N: Sliced base meshes
    for plane in planes:
        origin = plane.plane_origin
        normal = plane.unit_normal
        
        # slice_plane returns the portion of the mesh to the POSITIVE normal side.
        sliced_mesh = mesh.slice_plane(plane_origin=origin, plane_normal=normal, cap=True)
        
        # If the plane missed the mesh, slice_plane might return None or an empty mesh
        if sliced_mesh is None or sliced_mesh.is_empty:
            chunks.append(None)
        else:
            chunks.append(sliced_mesh)
            
    return chunks

from typing import Tuple
from models import Diagnostic
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus

def subtract_later_chunks(job_id: str, chunks: List[Optional[trimesh.Trimesh]]) -> Tuple[List[Optional[trimesh.Trimesh]], List[Diagnostic]]:
    """
    Subtracts all later valid chunks from each earlier chunk to prevent geometric overlaps.
    Returns the modified chunks and a list of diagnostics for empty or invalid results.
    """
    diagnostics = []
    
    # We must process chunks iteratively.
    # Note: To avoid mutating the array while referencing it, we process in-place cautiously.
    for i in range(len(chunks) - 1):
        if chunks[i] is None or chunks[i].is_empty:
            continue
            
        current_mesh = chunks[i]
        
        for j in range(i + 1, len(chunks)):
            if chunks[j] is None or chunks[j].is_empty:
                continue
                
            # Perform boolean subtraction (current_mesh - chunks[j])
            try:
                current_mesh = current_mesh.difference(chunks[j])
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
                current_mesh = None
                break
                
            if current_mesh is None or current_mesh.is_empty:
                diagnostics.append(Diagnostic(
                    job_id=job_id,
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.WARNING,
                    status=DiagnosticStatus.WARNING,
                    code="EMPTY_CHUNK_AFTER_SUBTRACTION",
                    message=f"Chunk {i} became completely empty after subtracting Chunk {j}.",
                    details={"chunk_i": i, "chunk_j": j}
                ))
                current_mesh = None
                break
                
            if not current_mesh.is_watertight:
                diagnostics.append(Diagnostic(
                    job_id=job_id,
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.WARNING,
                    status=DiagnosticStatus.WARNING,
                    code="NON_MANIFOLD_CHUNK",
                    message=f"Chunk {i} became non-manifold after subtracting Chunk {j}.",
                    details={"chunk_i": i, "chunk_j": j}
                ))
                # We do not nullify it, just warn.
                
        chunks[i] = current_mesh
        
    return chunks, diagnostics
