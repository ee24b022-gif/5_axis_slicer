from pydantic import BaseModel, Field
from typing import Dict, List
from enums import ExportStatus, GCodeDialect, DiagnosticStatus
from validation_model import ValidationDiagnostic

class ExportProvenance(BaseModel):
    """
    Immutable metadata trace ensuring verifiable lineage for generated output.
    """
    input_hash: str
    settings_revision: int
    profile_name: str
    dialect: GCodeDialect
    axis_mapping: Dict[str, str]
    status: ExportStatus
    diagnostics: List[ValidationDiagnostic] = Field(default_factory=list)
    safety_label: str

class ProvenanceBuilder:
    @staticmethod
    def build(
        input_hash: str,
        settings_revision: int,
        profile_name: str,
        dialect: GCodeDialect,
        axis_mapping: Dict[str, str],
        diagnostics: List[ValidationDiagnostic],
        is_prototype: bool
    ) -> ExportProvenance:
        
        # Determine if there are any blocking diagnostics
        is_blocking = any(d.status in (DiagnosticStatus.FAIL, DiagnosticStatus.NOT_IMPLEMENTED) for d in diagnostics)
        
        if is_blocking:
            status = ExportStatus.BLOCKED
            safety_label = "UNSAFE - BLOCKED BY DIAGNOSTICS"
        else:
            status = ExportStatus.READY
            if is_prototype:
                safety_label = "PROTOTYPE - USE WITH CAUTION"
            else:
                safety_label = "PRODUCTION - VERIFIED"
                
        return ExportProvenance(
            input_hash=input_hash,
            settings_revision=settings_revision,
            profile_name=profile_name,
            dialect=dialect,
            axis_mapping=axis_mapping,
            status=status,
            diagnostics=diagnostics,
            safety_label=safety_label
        )
