import math
from pydantic import BaseModel, Field, model_validator
from typing import Tuple
from enums import AngleUnit, RotationConvention

class SlicePlane(BaseModel):
    """
    Defines a rigorous kinematic slice-plane configuration for 5-axis/indexed multi-directional slicing.
    Validates orientation, orthogonality, and rotation limits.
    """
    plane_origin: Tuple[float, float, float] = Field(..., description="The (x,y,z) origin point of the slicing plane.")
    unit_normal: Tuple[float, float, float] = Field(..., description="The unit normal vector of the slicing plane.")
    
    angle_pair: Tuple[float, float] = Field(..., description="The two kinematic rotation angles.")
    angle_units: AngleUnit = Field(default=AngleUnit.DEGREES, description="Units for the angle pair.")
    rotation_convention: RotationConvention = Field(..., description="The kinematic rotation sequence.")
    
    local_x: Tuple[float, float, float] = Field(..., description="Local X axis vector in the plane.")
    local_y: Tuple[float, float, float] = Field(..., description="Local Y axis vector in the plane.")
    
    source_frame: str = Field(default="canonical", description="Identifier of the origin frame of reference.")

    @model_validator(mode='after')
    def validate_vectors(self) -> 'SlicePlane':
        """
        Validates that normal and local axes are precisely unit length,
        and that the entire coordinate system is mutually orthogonal.
        """
        # 1. Validate normal is unit length
        n_length = math.hypot(*self.unit_normal)
        if not math.isclose(n_length, 1.0, rel_tol=1e-5):
            raise ValueError(f"Normal vector must be a unit vector, got length {n_length}")
            
        # 2. Validate local axes are unit length
        x_length = math.hypot(*self.local_x)
        y_length = math.hypot(*self.local_y)
        if not math.isclose(x_length, 1.0, rel_tol=1e-5) or not math.isclose(y_length, 1.0, rel_tol=1e-5):
            raise ValueError("Local axes must be strict unit vectors.")
            
        # 3. Check orthogonality
        dot_nx = sum(a*b for a, b in zip(self.unit_normal, self.local_x))
        dot_ny = sum(a*b for a, b in zip(self.unit_normal, self.local_y))
        dot_xy = sum(a*b for a, b in zip(self.local_x, self.local_y))
        
        if not math.isclose(dot_nx, 0.0, abs_tol=1e-5) or not math.isclose(dot_ny, 0.0, abs_tol=1e-5):
            raise ValueError("Local axes are not perpendicular to the normal vector.")
            
        if not math.isclose(dot_xy, 0.0, abs_tol=1e-5):
            raise ValueError("Local X and Y axes are not orthogonal to each other.")
            
        return self

    @model_validator(mode='after')
    def validate_angle_ranges(self) -> 'SlicePlane':
        """
        Validates that the provided machine angles fall within realistic physical rotation bounds.
        Assuming maximum rotation is ±360 degrees or ±2π radians for standard indexed tables.
        """
        bound = 360.0 if self.angle_units == AngleUnit.DEGREES else 2 * math.pi
        a1, a2 = self.angle_pair
        
        # Enforce physical mechanical limit checks
        if not (-bound <= a1 <= bound) or not (-bound <= a2 <= bound):
            raise ValueError(f"Angle pair {self.angle_pair} exceeds valid mechanical rotational bounds (+/- {bound} {self.angle_units.value}).")
            
        return self
