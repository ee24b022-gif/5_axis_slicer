import os

def add_exports():
    path = "backend/models.py"
    with open(path, "r") as f:
        content = f.read()

    # Update enum imports
    if "ExportStatus" not in content:
        content = content.replace(
            "from enums import JobStatus, JobMode, JobStage, MeshFormat, ChunkValidity, DiagnosticSeverity, DiagnosticStatus",
            "from enums import JobStatus, JobMode, JobStage, MeshFormat, ChunkValidity, DiagnosticSeverity, DiagnosticStatus, ExportStatus"
        )

    # Add exports relationship to Job
    job_rel = '    diagnostics: Mapped[List["Diagnostic"]] = relationship(back_populates="job", cascade="all, delete-orphan")\n    exports: Mapped[List["Export"]] = relationship(back_populates="job", cascade="all, delete-orphan")'
    if 'exports: Mapped[List["Export"]] = relationship(back_populates="job"' not in content:
        content = content.replace('    diagnostics: Mapped[List["Diagnostic"]] = relationship(back_populates="job", cascade="all, delete-orphan")', job_rel, 1)

    # Add exports relationship to User
    user_rel = '    jobs: Mapped[List["Job"]] = relationship(back_populates="creator", cascade="all, delete-orphan")\n    exports: Mapped[List["Export"]] = relationship(back_populates="creator", cascade="all, delete-orphan")'
    if 'exports: Mapped[List["Export"]] = relationship(back_populates="creator"' not in content:
        content = content.replace('    jobs: Mapped[List["Job"]] = relationship(back_populates="creator", cascade="all, delete-orphan")', user_rel, 1)

    # Add Export model
    export_model = """
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
    
    job: Mapped["Job"] = relationship(back_populates="exports")
    creator: Mapped["User"] = relationship(back_populates="exports")

    __table_args__ = (
        CheckConstraint(
            "status != 'ready' OR storage_uri IS NOT NULL",
            name="ck_export_ready_storage_uri"
        ),
        Index(
            'ix_export_job_dialect_active',
            'job_id',
            'dialect',
            unique=True,
            sqlite_where=text("status != 'revoked'"),
            postgresql_where=text("status != 'revoked'")
        ),
    )
"""
    if "class Export" not in content:
        content += export_model

    with open(path, "w") as f:
        f.write(content)

add_exports()
