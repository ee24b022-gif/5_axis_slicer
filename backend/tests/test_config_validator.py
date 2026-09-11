import pytest
import uuid
from config_validator import validate_job_config
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus

def test_valid_configuration_passes():
    job_id = uuid.uuid4()
    
    # "lines" is supported, generate_supports is False
    settings = {
        "infill_pattern": "lines",
        "generate_supports": False,
        "layer_height": 0.2
    }
    
    diagnostics = validate_job_config(job_id, settings)
    assert len(diagnostics) == 0

def test_unsupported_supports_diagnostic():
    job_id = uuid.uuid4()
    settings = {
        "infill_pattern": "lines",
        "generate_supports": True
    }
    
    diagnostics = validate_job_config(job_id, settings)
    assert len(diagnostics) == 1
    
    diag = diagnostics[0]
    assert diag.code == "UNSUPPORTED_SUPPORTS"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.status == DiagnosticStatus.NOT_IMPLEMENTED
    assert diag.stage == JobStage.VALIDATION
    assert diag.job_id == job_id

def test_unsupported_infill_diagnostic():
    job_id = uuid.uuid4()
    settings = {
        "infill_pattern": "honeycomb",
        "generate_supports": False
    }
    
    diagnostics = validate_job_config(job_id, settings)
    assert len(diagnostics) == 1
    
    diag = diagnostics[0]
    assert diag.code == "UNSUPPORTED_INFILL"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.status == DiagnosticStatus.NOT_IMPLEMENTED
    assert diag.stage == JobStage.VALIDATION
    assert "honeycomb" in diag.details["requested_pattern"]

def test_multiple_unsupported_diagnostics():
    job_id = uuid.uuid4()
    # Trigger both blocks
    settings = {
        "infill_pattern": "grid",
        "generate_supports": True
    }
    
    diagnostics = validate_job_config(job_id, settings)
    assert len(diagnostics) == 2
    
    codes = [d.code for d in diagnostics]
    assert "UNSUPPORTED_SUPPORTS" in codes
    assert "UNSUPPORTED_INFILL" in codes
