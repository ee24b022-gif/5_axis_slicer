import pytest
from validation_model import ValidationDiagnostic, ValidationResult
from enums import DiagnosticStatus, DiagnosticSeverity, JobStage

def create_diagnostic(status, message, code):
    return ValidationDiagnostic(
        stage=JobStage.MESH_VALIDATION,
        severity=DiagnosticSeverity.INFO if status == DiagnosticStatus.PASS else (
            DiagnosticSeverity.WARNING if status == DiagnosticStatus.WARNING else DiagnosticSeverity.ERROR
        ),
        status=status,
        message=message,
        code=code
    )

def test_empty_diagnostics_pass():
    res = ValidationResult(diagnostics=[])
    assert res.aggregate_status == DiagnosticStatus.PASS
    assert res.is_blocking is False

def test_warning_escalation():
    res = ValidationResult(diagnostics=[
        create_diagnostic(DiagnosticStatus.PASS, "ok", "OK"),
        create_diagnostic(DiagnosticStatus.WARNING, "warn", "WARN")
    ])
    assert res.aggregate_status == DiagnosticStatus.WARNING
    assert res.is_blocking is False

def test_not_implemented_escalation():
    res = ValidationResult(diagnostics=[
        create_diagnostic(DiagnosticStatus.PASS, "ok", "OK"),
        create_diagnostic(DiagnosticStatus.WARNING, "warn", "WARN"),
        create_diagnostic(DiagnosticStatus.NOT_IMPLEMENTED, "missing", "NI")
    ])
    assert res.aggregate_status == DiagnosticStatus.NOT_IMPLEMENTED
    assert res.is_blocking is True

def test_fail_escalation():
    res = ValidationResult(diagnostics=[
        create_diagnostic(DiagnosticStatus.PASS, "ok", "OK"),
        create_diagnostic(DiagnosticStatus.NOT_IMPLEMENTED, "missing", "NI"),
        create_diagnostic(DiagnosticStatus.FAIL, "error", "ERR")
    ])
    assert res.aggregate_status == DiagnosticStatus.FAIL
    assert res.is_blocking is True

def test_is_blocking_property():
    res_pass = ValidationResult(diagnostics=[create_diagnostic(DiagnosticStatus.PASS, "ok", "OK")])
    assert not res_pass.is_blocking
    
    res_warn = ValidationResult(diagnostics=[create_diagnostic(DiagnosticStatus.WARNING, "warn", "WARN")])
    assert not res_warn.is_blocking
    
    res_ni = ValidationResult(diagnostics=[create_diagnostic(DiagnosticStatus.NOT_IMPLEMENTED, "ni", "NI")])
    assert res_ni.is_blocking
    
    res_fail = ValidationResult(diagnostics=[create_diagnostic(DiagnosticStatus.FAIL, "fail", "FAIL")])
    assert res_fail.is_blocking
