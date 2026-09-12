from pydantic import BaseModel, ConfigDict, Field
from typing import List, Tuple, Dict, Any
from enums import MeshFormat, JobMode, JobStatus, JobStage, DiagnosticSeverity, DiagnosticStatus, ExportStatus
from datetime import datetime
import uuid

class PreviewLayerResponse(BaseModel):
    id: uuid.UUID
    layer_idx: int
    z_height: float
    thickness: float
    is_support: bool
    preview_uri: str | None = None

    model_config = ConfigDict(from_attributes=True)

class PreviewResponse(BaseModel):
    job_id: uuid.UUID
    layers: List[PreviewLayerResponse]

class DiagnosticResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    chunk_id: uuid.UUID | None = None
    layer_id: uuid.UUID | None = None
    stage: JobStage
    severity: DiagnosticSeverity
    status: DiagnosticStatus
    code: str
    message: str
    details: Dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MeshResponse(BaseModel):
    id: uuid.UUID
    uploader_id: uuid.UUID
    content_hash: str
    format: MeshFormat
    size_bytes: int
    triangle_count: int
    bound_min_x: float
    bound_min_y: float
    bound_min_z: float
    bound_max_x: float
    bound_max_y: float
    bound_max_z: float

    model_config = ConfigDict(from_attributes=True)

class JobCreateRequest(BaseModel):
    mesh_id: uuid.UUID
    machine_profile_id: uuid.UUID
    mode: JobMode
    settings: Dict[str, Any] = Field(default_factory=dict)

class JobResponse(BaseModel):
    id: uuid.UUID
    creator_id: uuid.UUID
    mesh_id: uuid.UUID
    machine_profile_id: uuid.UUID
    mode: JobMode
    status: JobStatus
    progress: float
    checkpoint_data: Dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class FrameMetadata(BaseModel):
    """
    Standardizes canonical part-to-bed transformation persistence.
    Stored inside Job.settings and Export.export_metadata JSON columns.
    """
    input_hash: str = Field(..., description="SHA-256 hash of the input mesh bytes")
    transform_matrix: Tuple[
        Tuple[float, float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float, float],
        Tuple[float, float, float, float]
    ] = Field(..., description="Exact 4x4 affine transformation matrix applied to raw coordinates")
    
    # Mathematical origin parameters
    scale: float = Field(1.0, gt=0.0)
    rot_x_deg: float = Field(0.0)
    rot_y_deg: float = Field(0.0)
    rot_z_deg: float = Field(0.0)
    trans_x: float = Field(0.0)
    trans_y: float = Field(0.0)

class ExportResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    creator_id: uuid.UUID
    dialect: str
    status: ExportStatus
    storage_uri: str | None = None
    content_hash: str | None = None
    size_bytes: int | None = None
    export_metadata: Dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class MachineProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    revision: int
    dialect: str
    contract: Dict[str, Any]
    limits: Dict[str, Any]
    is_active: bool
    author_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class APIKeyCreateRequest(BaseModel):
    description: str | None = None
    scopes: List[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(None, description="Optional number of days until the key expires")

class APIKeyResponse(BaseModel):
    id: uuid.UUID
    prefix: str
    scopes: List[str]
    description: str | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    
    model_config = ConfigDict(from_attributes=True)

class APIKeyCreateResponse(APIKeyResponse):
    raw_key: str = Field(..., description="The raw API key. This will only be shown once.")

