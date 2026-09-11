import os
import re

def add_diagnostics():
    path = "backend/models.py"
    with open(path, "r") as f:
        content = f.read()

    # Update enum imports
    if "DiagnosticSeverity" not in content:
        content = content.replace(
            "from enums import JobStatus, JobMode, JobStage, MeshFormat, ChunkValidity",
            "from enums import JobStatus, JobMode, JobStage, MeshFormat, ChunkValidity, DiagnosticSeverity, DiagnosticStatus"
        )

    # Add diagnostics relationship to Job
    job_rel = '    diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="job", cascade="all, delete-orphan")\n\n    __table_args__ ='
    if 'diagnostics: Mapped[list["Diagnostic"]]' not in content:
        content = content.replace("    __table_args__ =", job_rel, 1)

    # Add diagnostics relationship to Chunk
    chunk_rel = '    job: Mapped["Job"] = relationship(back_populates="chunks")\n    diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="chunk", cascade="all, delete-orphan")'
    if 'diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="chunk"' not in content:
        content = content.replace('    job: Mapped["Job"] = relationship(back_populates="chunks")', chunk_rel, 1)

    # Add diagnostics relationship to Layer
    layer_rel = '    job: Mapped["Job"] = relationship(back_populates="layers")\n    diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="layer", cascade="all, delete-orphan")'
    if 'diagnostics: Mapped[list["Diagnostic"]] = relationship(back_populates="layer"' not in content:
        content = content.replace('    job: Mapped["Job"] = relationship(back_populates="layers")', layer_rel, 1)

    # Add Diagnostic model
    diagnostic_model = """
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
"""
    if "class Diagnostic" not in content:
        content += diagnostic_model

    with open(path, "w") as f:
        f.write(content)

add_diagnostics()
