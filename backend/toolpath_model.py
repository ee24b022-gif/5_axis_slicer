from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Tuple

class PathCategory(str, Enum):
    """Explicitly tracks the physical extrusion intent of a geometric structure."""
    PERIMETER = "perimeter"
    SOLID_INFILL = "solid_infill"
    INTERNAL_INFILL = "internal_infill"
    BRIM = "brim"
    TRAVEL = "travel"

class ToolpathSegment(BaseModel):
    """
    A single contiguous path of vectors possessing exactly one geometric intent.
    If intent changes (e.g., stopping extrusion to travel), a new segment is issued.
    """
    path_id: int = Field(..., description="Unique deterministic execution sequence index.")
    category: PathCategory = Field(..., description="The physical extrusion intent (e.g. perimeter vs travel).")
    coords: List[Tuple[float, float]] = Field(
        ..., 
        description="The physical (X, Y) vectors constructing this toolpath."
    )

class ToolpathLayer(BaseModel):
    """
    An isolated horizontal slice containing a deterministic execution sequence of vectors.
    """
    layer_id: int = Field(..., description="Z-stack index.")
    z_height: float = Field(..., description="The absolute physical Z height of this layer.")
    paths: List[ToolpathSegment] = Field(default_factory=list, description="Ordered paths executing this slice.")

class ToolpathJob(BaseModel):
    """
    The complete, serialized output structure of the 3-axis computation engine.
    """
    job_id: str = Field(..., description="The root identifier of the sliced job.")
    layers: List[ToolpathLayer] = Field(default_factory=list, description="The vertical slice stack.")
