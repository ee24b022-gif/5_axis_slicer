from typing import Dict, Any, List
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
from models import Diagnostic

def validate_job_config(job_id: str, settings: Dict[str, Any]) -> List[Diagnostic]:
    """
    Validates physical capability and feature configurations for a slicing job.
    Returns standard database Diagnostic models for unsupported or mismatched features.
    
    Args:
        job_id: The UUID of the job being configured.
        settings: The dynamic JSON configuration dictionary from the UI.
        
    Returns:
        List[Diagnostic]: Blockers that should halt the pipeline gracefully.
    """
    diagnostics = []
    
    # 1. Reject automated supports
    # Currently we rely exclusively on the user to provide pre-supported mesh models.
    if settings.get("generate_supports") is True:
        diagnostics.append(
            Diagnostic(
                job_id=job_id,
                stage=JobStage.VALIDATION,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.NOT_IMPLEMENTED,
                code="UNSUPPORTED_SUPPORTS",
                message="Automated support generation is currently unsupported. Please provide pre-supported geometry."
            )
        )
        
    # 2. Reject non-implemented infill patterns
    pattern = settings.get("infill_pattern", "lines")
    supported_patterns = ["lines"]
    
    if pattern not in supported_patterns:
        diagnostics.append(
            Diagnostic(
                job_id=job_id,
                stage=JobStage.VALIDATION,
                severity=DiagnosticSeverity.ERROR,
                status=DiagnosticStatus.NOT_IMPLEMENTED,
                code="UNSUPPORTED_INFILL",
                message=f"Infill pattern '{pattern}' is not implemented. Supported patterns: {supported_patterns}",
                details={"requested_pattern": pattern, "supported": supported_patterns}
            )
        )
        
    return diagnostics
