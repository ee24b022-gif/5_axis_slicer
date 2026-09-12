import pytest
from enums import ExportStatus, GCodeDialect, DiagnosticStatus, DiagnosticSeverity, JobStage
from validation_model import ValidationDiagnostic
from provenance_model import ProvenanceBuilder, ExportProvenance

def create_base_diagnostics():
    return [
        ValidationDiagnostic(
            stage=JobStage.MESH_VALIDATION,
            severity=DiagnosticSeverity.INFO,
            status=DiagnosticStatus.PASS,
            code="M-001",
            message="Mesh is manifold"
        )
    ]

def test_blocking_diagnostics_coerce_status():
    diagnostics = create_base_diagnostics()
    # Add a blocking diagnostic
    diagnostics.append(ValidationDiagnostic(
        stage=JobStage.POST_PROCESSING,
        severity=DiagnosticSeverity.CRITICAL,
        status=DiagnosticStatus.NOT_IMPLEMENTED,
        code="P-004",
        message="Unsupported mapping"
    ))
    
    provenance = ProvenanceBuilder.build(
        input_hash="deadbeef",
        settings_revision=1,
        profile_name="MyPrinter",
        dialect=GCodeDialect.MARLIN,
        axis_mapping={"x": "X"},
        diagnostics=diagnostics,
        is_prototype=False
    )
    
    assert provenance.status == ExportStatus.BLOCKED
    assert provenance.safety_label == "UNSAFE - BLOCKED BY DIAGNOSTICS"

def test_prototype_safety_labeling():
    diagnostics = create_base_diagnostics()
    
    provenance = ProvenanceBuilder.build(
        input_hash="deadbeef",
        settings_revision=1,
        profile_name="MyPrinter",
        dialect=GCodeDialect.MARLIN,
        axis_mapping={"x": "X"},
        diagnostics=diagnostics,
        is_prototype=True
    )
    
    assert provenance.status == ExportStatus.READY
    assert provenance.safety_label == "PROTOTYPE - USE WITH CAUTION"

def test_clean_production_build():
    diagnostics = create_base_diagnostics()
    
    provenance = ProvenanceBuilder.build(
        input_hash="deadbeef",
        settings_revision=1,
        profile_name="MyPrinter",
        dialect=GCodeDialect.MARLIN,
        axis_mapping={"x": "X"},
        diagnostics=diagnostics,
        is_prototype=False
    )
    
    assert provenance.status == ExportStatus.READY
    assert provenance.safety_label == "PRODUCTION - VERIFIED"
