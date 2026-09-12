import io
import trimesh
from typing import Dict, Any, Tuple, Callable
from enums import JobMode, JobStage, DiagnosticStatus, DiagnosticSeverity
from validation_model import ValidationDiagnostic, ValidationResult
from progress_model import StageProgressEvent

import transform_utils
import slicer_python

class JobCancelledError(Exception):
    """Raised when a job is cooperatively cancelled during execution."""
    pass

class GeometryApplicationService:
    @staticmethod
    def execute(
        job_id: str,
        file_bytes: bytes,
        job_mode: JobMode,
        job_settings: dict,
        machine_profile: dict,
        progress_callback: Callable[[StageProgressEvent], None] = None,
        is_cancelled: Callable[[], bool] = None
    ) -> Tuple[Dict[str, Any], list]:
        """
        Pure computation boundary for mesh processing and slicing.
        Returns:
            (result_payload, diagnostics_list)
        """
        diagnostics = []
        
        def emit(stage, progress, severity=None, status=None, code=None, message=None):
            if progress_callback:
                progress_callback(StageProgressEvent(
                    job_id=job_id,
                    stage=stage,
                    progress=progress,
                    severity=severity,
                    status=status,
                    code=code,
                    message=message
                ))

        def check_cancellation(stage: JobStage):
            if is_cancelled and is_cancelled():
                diagnostics.append(ValidationDiagnostic(
                    stage=stage,
                    severity=DiagnosticSeverity.WARNING,
                    status=DiagnosticStatus.FAIL,
                    code="X-001",
                    message="Job was cooperatively cancelled by user."
                ))
                raise JobCancelledError("Job was cooperatively cancelled.")
        
        try:
            emit(JobStage.MESH_VALIDATION, 0.0)
            check_cancellation(JobStage.MESH_VALIDATION)
            # 1. Load and Validate Mesh
            try:
                mesh = trimesh.load(io.BytesIO(file_bytes), file_type='stl')
                from mesh_structural_validator import validate_mesh_structure
                
                validated_mesh, raw_diags = validate_mesh_structure(mesh.vertices, mesh.faces)
                
                for d in raw_diags:
                    status = DiagnosticStatus.FAIL if d["severity"] == DiagnosticSeverity.ERROR else DiagnosticStatus.WARNING
                    diagnostics.append(ValidationDiagnostic(
                        stage=JobStage.MESH_VALIDATION,
                        severity=d["severity"],
                        status=status,
                        code=d["code"],
                        message=d["message"]
                    ))
                    
                mesh = validated_mesh
                if mesh is None:
                    # Execution halted by validator
                    return {}, diagnostics
                
                emit(JobStage.MESH_VALIDATION, 1.0)
                
            except Exception as e:
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.MESH_VALIDATION,
                    severity=DiagnosticSeverity.CRITICAL,
                    status=DiagnosticStatus.FAIL,
                    code="M-000",
                    message=f"Failed to load mesh: {str(e)}"
                ))
                return {}, diagnostics
                
            # Stop early if mesh validation has blocking errors
            val_result = ValidationResult(diagnostics=diagnostics)
            if val_result.is_blocking:
                return {}, diagnostics
                
            emit(JobStage.CANONICAL_FRAME, 0.0)
            check_cancellation(JobStage.CANONICAL_FRAME)
            # 2. Canonical Frame Alignment
            try:
                aligned_mesh, transform_mat = transform_utils.apply_canonical_transform(mesh)
                # Log transform applied
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.CANONICAL_FRAME,
                    severity=DiagnosticSeverity.INFO,
                    status=DiagnosticStatus.PASS,
                    code="C-001",
                    message="Canonical transform applied successfully."
                ))
                emit(JobStage.CANONICAL_FRAME, 1.0)
            except Exception as e:
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.CANONICAL_FRAME,
                    severity=DiagnosticSeverity.ERROR,
                    status=DiagnosticStatus.FAIL,
                    code="C-000",
                    message=f"Canonical transform failed: {str(e)}"
                ))
                return {}, diagnostics
                
            emit(JobStage.SECTIONING, 0.0)
            check_cancellation(JobStage.SECTIONING)
            # 3. Slicing
            # F-035/F-036
            try:
                # Re-export mesh to bytes to feed into slicer_python.slice_mesh
                # (since slice_mesh currently expects file_bytes)
                # In a real integration, slice_mesh should probably take the trimesh object directly
                # but for now we follow the existing API.
                
                export_bytes = io.BytesIO()
                aligned_mesh.export(export_bytes, file_type='stl')
                aligned_bytes = export_bytes.getvalue()
                
                # Using basic default settings for the fallback
                layer_height = job_settings.get("layer_height", 0.2)
                bed_center_z = job_settings.get("bed_center_z", 0.0)
                
                # Fallback path logic
                result = slicer_python.slice_mesh(
                    aligned_bytes,
                    layer_height,
                    bed_center_z
                )
                
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.INFO,
                    status=DiagnosticStatus.PASS,
                    code="S-001",
                    message="Slicing completed."
                ))
                emit(JobStage.SECTIONING, 1.0)
                # If slicer returned an open temp file, we must close it for multiprocess pickling
                if "gcode_file" in result and hasattr(result["gcode_file"], "read"):
                    # Seek to 0 and read string
                    result["gcode_file"].seek(0)
                    gcode_str = result["gcode_file"].read()
                    result["gcode_file"].close()
                    result["gcode_string"] = gcode_str
                    del result["gcode_file"]
                
                return {"toolpath_job": result}, diagnostics
                
            except Exception as e:
                diagnostics.append(ValidationDiagnostic(
                    stage=JobStage.SECTIONING,
                    severity=DiagnosticSeverity.ERROR,
                    status=DiagnosticStatus.FAIL,
                    code="S-000",
                    message=f"Slicing failed: {str(e)}"
                ))
                return {}, diagnostics

        except JobCancelledError:
            # We gracefully return empty payload, but include the cancellation diagnostic which was already appended.
            return {"status": "cancelled"}, diagnostics
