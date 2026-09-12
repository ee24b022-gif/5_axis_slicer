from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus

class StageProgressEvent(BaseModel):
    """
    Standardized payload for broadcasting worker slicing progress.
    Designed for consistent serialization to SSE streams or Redis channels.
    """
    job_id: str
    stage: JobStage
    progress: float = Field(..., ge=0.0, le=1.0, description="Percentage complete for this stage (0.0 to 1.0)")
    
    # Optional context mapping to specific chunks or layers during indexed slicing
    chunk_id: Optional[str] = None
    layer_id: Optional[str] = None
    
    # Optional diagnostic bubbling for in-stream warnings/errors
    severity: Optional[DiagnosticSeverity] = None
    status: Optional[DiagnosticStatus] = None
    code: Optional[str] = None
    message: Optional[str] = None
    
    # Enforce UTC timestamps for ordering safety
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }
