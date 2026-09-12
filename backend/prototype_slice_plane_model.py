from pydantic import BaseModel, Field, model_validator
import math
from enum import Enum

class AngleUnit(str, Enum):
    DEGREES = "degrees"
    RADIANS = "radians"

class RotationConvention(str, Enum):
    AC_TABLE = "AC_TABLE"
    BC_TABLE = "BC_TABLE"
    AB_HEAD = "AB_HEAD"

class SlicePlane(BaseModel):
    plane_origin: tuple[float, float, float] = Field(..., description="The (x,y,z) origin point of the slicing plane.")
    unit_normal: tuple[float, float, float] = Field(..., description="The unit normal vector of the slicing plane.")
    angle_pair: tuple[float, float] = Field(..., description="The two kinematic rotation angles.")
    angle_units: AngleUnit = Field(default=AngleUnit.DEGREES, description="Units for the angle pair.")
    rotation_convention: RotationConvention = Field(..., description="The kinematic rotation sequence.")
    local_x: tuple[float, float, float] = Field(..., description="Local X axis vector in the plane.")
    local_y: tuple[float, float, float] = Field(..., description="Local Y axis vector in the plane.")
    source_frame: str = Field(default="canonical", description="Identifier of the origin frame of reference.")

    @model_validator(mode='after')
    def validate_vectors(self) -> 'SlicePlane':
        # Validate unit normal
        n_length = math.hypot(*self.unit_normal)
        if not math.isclose(n_length, 1.0, rel_tol=1e-5):
            raise ValueError(f"Normal vector must be a unit vector, got length {n_length}")
            
        # Validate local axes
        x_length = math.hypot(*self.local_x)
        y_length = math.hypot(*self.local_y)
        if not math.isclose(x_length, 1.0, rel_tol=1e-5) or not math.isclose(y_length, 1.0, rel_tol=1e-5):
            raise ValueError("Local axes must be unit vectors.")
            
        # Check orthogonality
        dot_x = sum(a*b for a, b in zip(self.unit_normal, self.local_x))
        dot_y = sum(a*b for a, b in zip(self.unit_normal, self.local_y))
        dot_xy = sum(a*b for a, b in zip(self.local_x, self.local_y))
        
        if not math.isclose(dot_x, 0.0, abs_tol=1e-5) or not math.isclose(dot_y, 0.0, abs_tol=1e-5):
            raise ValueError("Local axes are not perpendicular to normal.")
        if not math.isclose(dot_xy, 0.0, abs_tol=1e-5):
            raise ValueError("Local X and Y axes are not orthogonal to each other.")
            
        return self

    @model_validator(mode='after')
    def validate_angle_ranges(self) -> 'SlicePlane':
        # Simple bounds check, assuming [-360, 360] is a safe limit for valid angle configs
        bound = 360.0 if self.angle_units == AngleUnit.DEGREES else 2*math.pi
        a1, a2 = self.angle_pair
        if not (-bound <= a1 <= bound) or not (-bound <= a2 <= bound):
            raise ValueError("Angle pair exceeds valid rotational bounds.")
        return self

plane = SlicePlane(
    plane_origin=(0.0, 0.0, 0.0),
    unit_normal=(0.0, 0.0, 1.0),
    angle_pair=(0.0, 0.0),
    angle_units=AngleUnit.DEGREES,
    rotation_convention=RotationConvention.AC_TABLE,
    local_x=(1.0, 0.0, 0.0),
    local_y=(0.0, 1.0, 0.0),
)
print(plane.model_dump_json(indent=2))
