import pytest
import json
from pydantic import BaseModel
from enums import (
    UserRole,
    JobStatus,
    JobMode,
    MeshFormat,
    ChunkValidity,
    DiagnosticSeverity,
    DiagnosticStatus,
    JobStage,
    ExportStatus,
    TokenStatus
)

def test_enum_string_values():
    assert UserRole.ADMIN == "admin"
    assert JobStatus.PENDING == "pending"
    assert JobMode.THREE_AXIS == "three_axis"
    assert MeshFormat.STL_BINARY == "stl_binary"
    assert ChunkValidity.VALID == "valid"
    assert DiagnosticSeverity.CRITICAL == "critical"
    assert DiagnosticStatus.NOT_IMPLEMENTED == "not_implemented"
    assert JobStage.ARTIFACT_PERSISTENCE == "artifact_persistence"
    assert ExportStatus.READY == "ready"
    assert TokenStatus.ACTIVE == "active"

def test_pydantic_serialization():
    class DummyModel(BaseModel):
        role: UserRole
        status: JobStatus
        mode: JobMode
        format: MeshFormat
        chunk: ChunkValidity
        diag_sev: DiagnosticSeverity
        diag_stat: DiagnosticStatus
        stage: JobStage
        export: ExportStatus
        token: TokenStatus

    model = DummyModel(
        role=UserRole.USER,
        status=JobStatus.RUNNING,
        mode=JobMode.INDEXED_MULTIDIRECTIONAL,
        format=MeshFormat.STL_BINARY,
        chunk=ChunkValidity.INVALID,
        diag_sev=DiagnosticSeverity.INFO,
        diag_stat=DiagnosticStatus.WARNING,
        stage=JobStage.CHUNK_CONSTRUCTION,
        export=ExportStatus.BLOCKED,
        token=TokenStatus.EXPIRED
    )

    serialized = model.model_dump()
    assert serialized["role"] == "user"
    assert serialized["status"] == "running"
    assert serialized["mode"] == "indexed_multidirectional"
    assert serialized["format"] == "stl_binary"
    assert serialized["chunk"] == "invalid"
    assert serialized["diag_sev"] == "info"
    assert serialized["diag_stat"] == "warning"
    assert serialized["stage"] == "chunk_construction"
    assert serialized["export"] == "blocked"
    assert serialized["token"] == "expired"

    json_data = model.model_dump_json()
    parsed = json.loads(json_data)
    
    assert parsed["role"] == "user"
    assert parsed["status"] == "running"
    assert parsed["mode"] == "indexed_multidirectional"
    assert parsed["format"] == "stl_binary"
    assert parsed["chunk"] == "invalid"
    assert parsed["diag_sev"] == "info"
    assert parsed["diag_stat"] == "warning"
    assert parsed["stage"] == "chunk_construction"
    assert parsed["export"] == "blocked"
    assert parsed["token"] == "expired"
