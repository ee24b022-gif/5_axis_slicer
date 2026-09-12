from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Tuple
from enums import RotationConvention

class MachineContract(BaseModel):
    """
    Defines the kinematic and procedural contract of a MachineProfile.
    Enforces that axis names, units, centers, and command templates are consistent.
    """
    calibration_revision: int = Field(..., description="Version of the physical calibration.")
    kinematic_convention: RotationConvention = Field(..., description="Kinematic structure of the machine.")
    units: str = Field(..., description="Units for coordinates, e.g., 'mm'.")
    axis_names: List[str] = Field(..., min_length=1, description="List of axis names, e.g., ['X', 'Y', 'Z', 'B', 'C'].")
    axis_directions: Dict[str, int] = Field(..., description="Mapping of axis name to direction (1 or -1).")
    zero_positions: Dict[str, float] = Field(..., description="Mapping of axis name to its zero position.")
    table_centers: Dict[str, float] = Field(default_factory=dict, description="Optional center coordinates for rotary axes.")
    command_templates: Dict[str, str] = Field(..., description="G-Code templates like 'linear_move'.")

    @model_validator(mode='after')
    def validate_axes_consistency(self) -> 'MachineContract':
        axes_set = set(self.axis_names)
        
        dir_keys = set(self.axis_directions.keys())
        if dir_keys != axes_set:
            missing = axes_set - dir_keys
            extra = dir_keys - axes_set
            raise ValueError(f"axis_directions must match axis_names exactly. Missing: {missing}, Extra: {extra}")
            
        zero_keys = set(self.zero_positions.keys())
        if zero_keys != axes_set:
            missing = axes_set - zero_keys
            extra = zero_keys - axes_set
            raise ValueError(f"zero_positions must match axis_names exactly. Missing: {missing}, Extra: {extra}")
            
        for axis, direction in self.axis_directions.items():
            if direction not in (1, -1):
                raise ValueError(f"Axis direction for {axis} must be 1 or -1. Got {direction}")
                
        return self

class MachineLimits(BaseModel):
    """
    Defines the physical travel limits of a MachineProfile.
    """
    ranges: Dict[str, Tuple[float, float]] = Field(..., description="Mapping of axis name to (min, max) range.")

    @model_validator(mode='after')
    def validate_ranges(self) -> 'MachineLimits':
        for axis, (min_val, max_val) in self.ranges.items():
            if min_val > max_val:
                raise ValueError(f"Limit for {axis} has min > max ({min_val} > {max_val})")
        return self
