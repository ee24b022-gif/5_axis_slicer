import pytest
from enums import JobStatus, ExportStatus, DiagnosticStatus, DiagnosticSeverity, JobStage, GCodeDialect
from export_gate import ExportGateService

class MockMachineProfile:
    def __init__(self, dialect):
        self.dialect = dialect

class MockDiagnostic:
    def __init__(self, status):
        self.stage = JobStage.VALIDATION
        self.severity = DiagnosticSeverity.CRITICAL
        self.status = status
        self.code = "TEST-01"
        self.message = "Test"
        self.details = {}

class MockJob:
    def __init__(self, status, dialect, diagnostics=None):
        self.status = status
        self.machine_profile = MockMachineProfile(dialect)
        self.diagnostics = diagnostics or []

class MockExport:
    def __init__(self, status, dialect, metadata=None):
        self.status = status
        self.dialect = dialect
        self.export_metadata = metadata or {}

def test_gate_blocks_incomplete_jobs():
    job = MockJob(status=JobStatus.PARTIAL, dialect=GCodeDialect.MARLIN)
    export = MockExport(status=ExportStatus.READY, dialect=GCodeDialect.MARLIN)
    
    allowed, details = ExportGateService.evaluate(job, export)
    assert not allowed
    assert "Job is not complete" in details["reason"]

def test_gate_blocks_dialect_mismatch():
    job = MockJob(status=JobStatus.COMPLETE, dialect=GCodeDialect.MARLIN)
    export = MockExport(status=ExportStatus.READY, dialect=GCodeDialect.KLIPPER)
    
    allowed, details = ExportGateService.evaluate(job, export)
    assert not allowed
    assert "Dialect mismatch" in details["reason"]

def test_gate_blocks_on_blocking_diagnostic():
    job = MockJob(
        status=JobStatus.COMPLETE, 
        dialect=GCodeDialect.MARLIN,
        diagnostics=[MockDiagnostic(DiagnosticStatus.FAIL)]
    )
    export = MockExport(status=ExportStatus.READY, dialect=GCodeDialect.MARLIN)
    
    allowed, details = ExportGateService.evaluate(job, export)
    assert not allowed
    assert "blocking diagnostics" in details["reason"]
    assert "UNSAFE" in details["safety_label"]

def test_gate_passes_ready_prototype():
    job = MockJob(status=JobStatus.COMPLETE, dialect=GCodeDialect.MARLIN)
    export = MockExport(
        status=ExportStatus.READY, 
        dialect=GCodeDialect.MARLIN,
        metadata={"status": ExportStatus.READY.value, "safety_label": "PROTOTYPE - USE WITH CAUTION"}
    )
    
    allowed, details = ExportGateService.evaluate(job, export)
    assert allowed
    assert details["safety_label"] == "PROTOTYPE - USE WITH CAUTION"

def test_gate_blocks_on_provenance_blocked():
    job = MockJob(status=JobStatus.COMPLETE, dialect=GCodeDialect.MARLIN)
    export = MockExport(
        status=ExportStatus.READY, 
        dialect=GCodeDialect.MARLIN,
        metadata={"status": ExportStatus.BLOCKED.value, "safety_label": "UNSAFE - BLOCKED BY DIAGNOSTICS"}
    )
    
    allowed, details = ExportGateService.evaluate(job, export)
    assert not allowed
    assert "blocked by provenance builder" in details["reason"]
    assert "UNSAFE" in details["safety_label"]
