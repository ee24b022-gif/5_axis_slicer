from pydantic import BaseModel, Field
from typing import List, Tuple

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
