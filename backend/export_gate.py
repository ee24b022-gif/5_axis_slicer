from models import Job, Export
from enums import JobStatus, ExportStatus
from validation_model import ValidationResult, ValidationDiagnostic
from typing import Dict, Any, Tuple

class ExportGateService:
    @staticmethod
    def evaluate(job: Job, export: Export) -> Tuple[bool, Dict[str, Any]]:
        """
        Gate logic for export retrieval.
        Returns (is_allowed, details_dict)
        """
        if job.status != JobStatus.COMPLETE:
            return False, {"reason": f"Job is not complete. Current status: {job.status.value}"}
            
        if export.status != ExportStatus.READY:
            return False, {"reason": f"Export is not ready. Current status: {export.status.value}"}
            
        if export.dialect != job.machine_profile.dialect:
            return False, {"reason": "Dialect mismatch between export and machine profile."}
            
        # Reconstruct diagnostics to double-check safety
        diagnostics = []
        if getattr(job, 'diagnostics', None):
            for d in job.diagnostics:
                diagnostics.append(ValidationDiagnostic(
                    stage=d.stage,
                    severity=d.severity,
                    status=d.status,
                    code=d.code,
                    message=d.message,
                    details=d.details or {}
                ))
            
        validation_result = ValidationResult(diagnostics=diagnostics)
        if validation_result.is_blocking:
            return False, {"reason": "Job contains blocking diagnostics", "safety_label": "UNSAFE - BLOCKED BY DIAGNOSTICS"}
            
        metadata = export.export_metadata or {}
        
        # Check export metadata provenance status
        if metadata.get("status") == ExportStatus.BLOCKED.value:
            return False, {"reason": "Export blocked by provenance builder", "safety_label": metadata.get("safety_label", "UNSAFE")}
            
        safety_label = metadata.get("safety_label", "PRODUCTION - VERIFIED")
        
        return True, {
            "reason": None,
            "safety_label": safety_label,
            "metadata": metadata
        }
