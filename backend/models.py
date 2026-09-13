from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import numpy as np
import uuid
from sqlalchemy import String, Boolean, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column
from database import Base, UTCDateTime
from mixins import TimestampMixin, SoftDeleteMixin
from enums import UserRole, MeshFormat, JobMode, JobStatus

from sqlalchemy import ForeignKey, Float, Integer, BigInteger, String, JSON, Boolean, UniqueConstraint, CheckConstraint
from datetime import datetime
from sqlalchemy.orm import relationship, validates
from enums import JobStatus, JobMode, JobStage, MeshFormat, ChunkValidity, DiagnosticSeverity, DiagnosticStatus, ExportStatus

# 1. Machine & Job Configurations
@dataclass
class SlicerMachineProfile:
    """Defines the physical limits and configuration of the 5-axis machine."""
    max_feedrate_xy: float = 3000.0   # mm/min
    max_feedrate_z: float = 300.0     # mm/min
    max_feedrate_uv: float = 1800.0   # deg/min (rotary axes)
    max_accel_xy: float = 500.0       # mm/s^2
    nozzle_diameter: float = 0.4      # mm
    filament_diameter: float = 1.75   # mm
    # Envelope for collision (cylinder approximation)
    nozzle_length: float = 40.0
    nozzle_holder_radius: float = 5.0

@dataclass
class SurfaceFieldConfig:
    """Defines the sinusoidal surface field parameters."""
    amplitude: float = 0.0
    wave_length_x: float = 50.0  # inverse of frequency
    wave_length_y: float = 50.0
    phase_x: float = 0.0
    phase_y: float = 0.0
    fade_height: float = 15.0

# 2. Geometry & Mesh Models
@dataclass
class CanonicalMesh:
    """Standardized representation of the input mesh."""
    vertices: np.ndarray  # Shape: (N, 3)
    faces: np.ndarray     # Shape: (M, 3)
    normals: np.ndarray   # Shape: (M, 3)
    bounds_min: Tuple[float, float, float]
    bounds_max: Tuple[float, float, float]

@dataclass
class SurfaceSample:
    """A specific point evaluated on the Surface Field."""
    position: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    gradient_magnitude: float
    curvature: float
    is_valid: bool = True

@dataclass
class SliceFrame:
    """Local coordinate frame for a field-aware layer."""
    layer_idx: int
    z_base: float
    effective_thickness: float
    field_normal: Tuple[float, float, float]

# 3. Path & Kinematics Models
@dataclass
class FeaturePath:
    """Authoritative representation of a toolpath feature."""
    points: List[Tuple[float, float, float]]
    normals: List[Tuple[float, float, float]]
    layer_idx: int
    feature_type: str  # 'perimeter', 'infill', 'solid_infill', 'travel'
    path_id: int
    target_bead_width: float = 0.4
    effective_thickness: float = 0.2
    is_travel: bool = False

@dataclass
class MachinePose:
    """A mechanically valid pose for the machine."""
    x: float
    y: float
    z: float
    u: float  # Primary rotary (e.g., A or B axis)
    v: float  # Secondary rotary (e.g., C axis)
    feedrate_limit: float
    is_valid: bool = True

# 4. Collision & Diagnostics
@dataclass
class CollisionReport:
    """Report generated if a sweep test fails."""
    path_id: int
    layer_idx: int
    point_index: int
    clearance: float
    limiting_surface: str  # 'bed', 'part', 'machine_limit'
    suggested_remedy: str

@dataclass
class SliceJobResult:
    """The final result of the slicing job to be sent to the frontend."""
    job_id: str
    feature_paths: List[FeaturePath]
    gcode: str
    diagnostics: List[str]
    collision_reports: List[CollisionReport]
    stage_timings: Dict[str, float] = field(default_factory=dict)


# 5. Database Models
class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'users'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLAlchemyEnum(UserRole), default=UserRole.USER, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_keys: Mapped[List["APIKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    meshes: Mapped[List["Mesh"]] = relationship(back_populates="uploader", cascade="all, delete-orphan")
    machine_profiles: Mapped[List["MachineProfile"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    jobs: Mapped[List["Job"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    exports: Mapped[List["Export"]] = relationship(back_populates="creator", cascade="all, delete-orphan")


class Chunk(Base, TimestampMixin):
    __tablename__ = 'chunks'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    source_plane: Mapped[dict] = mapped_column(JSON, nullable=False)
    transform_matrix: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    
    layer_idx_min: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_idx_max: Mapped[int] = mapped_column(Integer, nullable=False)
    min_z: Mapped[float] = mapped_column(Float, nullable=False)
    max_z: Mapped[float] = mapped_column(Float, nullable=False)
    
    validity: Mapped[ChunkValidity] = mapped_column(SQLAlchemyEnum(ChunkValidity), default=ChunkValidity.PENDING, nullable=False)
    last_completed_layer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    triangle_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    
    job: Mapped["Job"] = relationship(back_populates="chunks")
    diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="chunk", cascade="all, delete-orphan")


    __table_args__ = (
        UniqueConstraint('job_id', 'chunk_idx', name='uq_job_chunk_idx'),
    )

    @validates('transform_matrix')
    def validate_transform_matrix(self, key, value):
        if not isinstance(value, list):
            raise ValueError("Transform matrix must be a list")
        if len(value) != 16:
            raise ValueError("Transform matrix must be a flat 16-element list representing a 4x4 matrix")
        for v in value:
            if not isinstance(v, (int, float)):
                raise ValueError("Transform matrix elements must be numbers")
        return value

class Layer(Base, TimestampMixin):
    __tablename__ = 'layers'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    layer_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    z_height: Mapped[float] = mapped_column(Float, nullable=False)
    thickness: Mapped[float] = mapped_column(Float, nullable=False)
    is_planar: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_support: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gcode_offset: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    preview_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    job: Mapped["Job"] = relationship(back_populates="layers")
    diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="layer", cascade="all, delete-orphan")

class APIKey(Base, TimestampMixin):
    __tablename__ = 'api_keys'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    user: Mapped["User"] = relationship(back_populates="api_keys")

class RefreshToken(Base, TimestampMixin):
    __tablename__ = 'refresh_tokens'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True)
    
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
    replaced_by: Mapped[Optional["RefreshToken"]] = relationship(
        "RefreshToken",
        remote_side=[id],
        backref="replaces"
    )

class Mesh(Base, TimestampMixin):
    __tablename__ = 'meshes'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    uploader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    storage_uri: Mapped[str] = mapped_column(String, nullable=False)
    format: Mapped[MeshFormat] = mapped_column(nullable=False, default=MeshFormat.STL_BINARY)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    triangle_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bound_min_x: Mapped[float] = mapped_column(Float, nullable=False)
    bound_min_y: Mapped[float] = mapped_column(Float, nullable=False)
    bound_min_z: Mapped[float] = mapped_column(Float, nullable=False)
    bound_max_x: Mapped[float] = mapped_column(Float, nullable=False)
    bound_max_y: Mapped[float] = mapped_column(Float, nullable=False)
    bound_max_z: Mapped[float] = mapped_column(Float, nullable=False)
    cleaned_up_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    
    uploader: Mapped["User"] = relationship(back_populates="meshes")
    jobs: Mapped[List["Job"]] = relationship(back_populates="mesh")

class MachineProfile(Base, TimestampMixin):
    __tablename__ = 'machine_profiles'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    dialect: Mapped[str] = mapped_column(String, nullable=False)
    contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    limits: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    author: Mapped["User"] = relationship(back_populates="machine_profiles")
    jobs: Mapped[List["Job"]] = relationship(back_populates="machine_profile")
    
    __table_args__ = (
        UniqueConstraint('name', 'revision', name='uq_machine_profile_name_revision'),
    )

    @validates('contract')
    def validate_contract(self, key, value):
        from machine_profile_model import MachineContract
        try:
            MachineContract(**value)
        except Exception as e:
            raise ValueError(f"Invalid machine contract: {e}")
        return value

    @validates('limits')
    def validate_limits(self, key, value):
        from machine_profile_model import MachineLimits
        try:
            MachineLimits(**value)
        except Exception as e:
            raise ValueError(f"Invalid machine limits: {e}")
        return value

class Job(Base, TimestampMixin):
    __tablename__ = 'jobs'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mesh_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meshes.id", ondelete="RESTRICT"), nullable=False)
    machine_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("machine_profiles.id", ondelete="RESTRICT"), nullable=False)
    mode: Mapped[JobMode] = mapped_column(nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False)
    engine_revision: Mapped[str] = mapped_column(String, nullable=False)
    input_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[JobStatus] = mapped_column(nullable=False, default=JobStatus.PENDING)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    checkpoint_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    
    creator: Mapped["User"] = relationship(back_populates="jobs")
    mesh: Mapped["Mesh"] = relationship(back_populates="jobs")
    machine_profile: Mapped["MachineProfile"] = relationship(back_populates="jobs")
    chunks: Mapped[List["Chunk"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    layers: Mapped[List["Layer"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    diagnostics: Mapped[List["Diagnostic"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    exports: Mapped[List["Export"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint(
            "(status NOT IN ('COMPLETE', 'FAILED', 'CANCELLED')) OR (completed_at IS NOT NULL)",
            name="ck_job_terminal_status_completed_at"
        ),
    )

from sqlalchemy import Index

class Diagnostic(Base, TimestampMixin):
    __tablename__ = 'diagnostics'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True)
    layer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("layers.id", ondelete="CASCADE"), nullable=True)
    
    stage: Mapped[JobStage] = mapped_column(SQLAlchemyEnum(JobStage), nullable=False)
    severity: Mapped[DiagnosticSeverity] = mapped_column(SQLAlchemyEnum(DiagnosticSeverity), nullable=False)
    status: Mapped[DiagnosticStatus] = mapped_column(SQLAlchemyEnum(DiagnosticStatus), nullable=False)
    
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    job: Mapped["Job"] = relationship(back_populates="diagnostics")
    chunk: Mapped[Optional["Chunk"]] = relationship(back_populates="diagnostics")
    layer: Mapped[Optional["Layer"]] = relationship(back_populates="diagnostics")

    __table_args__ = (
        Index('ix_diagnostics_job_id_stage', 'job_id', 'stage'),
        Index('ix_diagnostics_job_id_severity_status', 'job_id', 'severity', 'status'),
    )

    @validates('chunk', 'layer')
    def validate_cross_job(self, key, value):
        if value is not None:
            # If both this diagnostic and the chunk/layer have a job_id set, they must match
            if self.job_id is not None and getattr(value, 'job_id', None) is not None:
                if self.job_id != value.job_id:
                    raise ValueError(f"Diagnostic chunk/layer belongs to a different job")
        return value
        
    @validates('job_id')
    def validate_job_id(self, key, value):
        if value is not None:
            if getattr(self, 'chunk', None) is not None and self.chunk.job_id is not None:
                if value != self.chunk.job_id:
                    raise ValueError("Diagnostic chunk/layer belongs to a different job")
            if getattr(self, 'layer', None) is not None and self.layer.job_id is not None:
                if value != self.layer.job_id:
                    raise ValueError("Diagnostic chunk/layer belongs to a different job")
        return value

from sqlalchemy import text

class Export(Base, TimestampMixin):
    __tablename__ = 'exports'
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    dialect: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ExportStatus] = mapped_column(SQLAlchemyEnum(ExportStatus), nullable=False, default=ExportStatus.PENDING)
    
    storage_uri: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    export_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    cleaned_up_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(timezone=True), nullable=True)
    
    job: Mapped["Job"] = relationship(back_populates="exports")
    creator: Mapped["User"] = relationship(back_populates="exports")

    __table_args__ = (
        CheckConstraint(
            "status != 'READY' OR storage_uri IS NOT NULL",
            name="ck_export_ready_storage_uri"
        ),
        Index(
            'ix_export_job_dialect_active',
            'job_id',
            'dialect',
            unique=True,
            sqlite_where=text("status != 'REVOKED'"),
            postgresql_where=text("status != 'REVOKED'")
        ),
    )
