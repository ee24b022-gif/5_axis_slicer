from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Tuple

class PathCategory(str, Enum):
    PERIMETER = "perimeter"
    SOLID_INFILL = "solid_infill"
    INTERNAL_INFILL = "internal_infill"
    BRIM = "brim"
    TRAVEL = "travel"

class ToolpathSegment(BaseModel):
    path_id: int
    category: PathCategory
    # List of (X, Y) coordinates.
    coords: List[Tuple[float, float]]

class ToolpathLayer(BaseModel):
    layer_id: int
    z_height: float
    paths: List[ToolpathSegment] = Field(default_factory=list)

class ToolpathJob(BaseModel):
    job_id: str
    layers: List[ToolpathLayer] = Field(default_factory=list)

job = ToolpathJob(
    job_id="test",
    layers=[
        ToolpathLayer(
            layer_id=0,
            z_height=0.2,
            paths=[
                ToolpathSegment(path_id=0, category=PathCategory.PERIMETER, coords=[(0,0), (10,0)]),
                ToolpathSegment(path_id=1, category=PathCategory.TRAVEL, coords=[(10,0), (15,0)])
            ]
        )
    ]
)
print(job.model_dump_json(indent=2))
