from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
from models import Diagnostic
from typing import Dict, Any, List

def validate_job_config(job_id, settings: Dict[str, Any]) -> List[Diagnostic]:
    diagnostics = []
    
    # 1. Reject automated supports
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

