from pydantic import BaseModel, Field
from typing import List, Dict, Any
from enums import DiagnosticStatus, DiagnosticSeverity, JobStage

class ValidationDiagnostic(BaseModel):
    stage: JobStage
    severity: DiagnosticSeverity
    status: DiagnosticStatus
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)

class ValidationResult(BaseModel):
    diagnostics: List[ValidationDiagnostic] = []

    @property
    def aggregate_status(self) -> DiagnosticStatus:
        if not self.diagnostics:
            return DiagnosticStatus.PASS
            
        statuses = [d.status for d in self.diagnostics]
        
        if DiagnosticStatus.FAIL in statuses:
            return DiagnosticStatus.FAIL
        if DiagnosticStatus.NOT_IMPLEMENTED in statuses:
            return DiagnosticStatus.NOT_IMPLEMENTED
        if DiagnosticStatus.WARNING in statuses:
            return DiagnosticStatus.WARNING
            
        return DiagnosticStatus.PASS
        
    @property
    def is_blocking(self) -> bool:
        agg = self.aggregate_status
        return agg in (DiagnosticStatus.FAIL, DiagnosticStatus.NOT_IMPLEMENTED)
