import pytest
from pydantic import ValidationError
import json
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
from progress_model import StageProgressEvent
from datetime import datetime, timezone

def test_progress_event_serialization():
    # Valid mid-processing event
    event = StageProgressEvent(
        job_id="job_123",
        stage=JobStage.SECTIONING,
        progress=0.5
    )
    
    # Should serialize safely to JSON
    json_str = event.model_dump_json()
    data = json.loads(json_str)
    
    assert data["job_id"] == "job_123"
    assert data["stage"] == JobStage.SECTIONING.value
    assert data["progress"] == 0.5
    assert "timestamp" in data

def test_progress_event_with_diagnostic():
    # Progress event that carries a warning payload
    event = StageProgressEvent(
        job_id="job_456",
        stage=JobStage.MESH_VALIDATION,
        progress=1.0,
        severity=DiagnosticSeverity.WARNING,
        status=DiagnosticStatus.WARNING,
        code="M-002",
        message="Non-manifold edge detected"
    )
    
    json_str = event.model_dump_json()
    data = json.loads(json_str)
    
    assert data["severity"] == DiagnosticSeverity.WARNING.value
    assert data["code"] == "M-002"
    assert data["message"] == "Non-manifold edge detected"

def test_progress_validation_bounds():
    # Negative progress should raise ValidationError
    with pytest.raises(ValidationError):
        StageProgressEvent(
            job_id="job_789",
            stage=JobStage.SECTIONING,
            progress=-0.1
        )
        
    # Progress above 1.0 should raise ValidationError
    with pytest.raises(ValidationError):
        StageProgressEvent(
            job_id="job_789",
            stage=JobStage.SECTIONING,
            progress=1.5
        )
