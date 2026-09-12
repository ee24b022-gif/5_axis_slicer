from pydantic import BaseModel, Field
from typing import Tuple
from enums import AngleUnit, RotationConvention
from slice_plane_model import SlicePlane

class LogicalPose(BaseModel):
    """
    A pure geometric representation of a machine's required kinematic orientation.
    By explicitly retaining the convention, units, and rotation order, we avoid 
    the dangerous assumption of blindly mapping (theta, phi) directly to 
    stepper motors (e.g. A/B vs U/V).
    """
    angles: Tuple[float, float] = Field(..., description="The two kinematic angles required to achieve the pose.")
    units: AngleUnit = Field(..., description="The angular unit system of the angles.")
    convention: RotationConvention = Field(..., description="The specific rotation convention required (e.g., BC_TABLE).")
    rotation_order: str = Field(..., description="The mathematical rotation order, e.g., 'Rz(C) * Ry(B)'.")
    source_origin: Tuple[float, float, float] = Field(..., description="The physical translation origin of the source slice plane.")
    source_normal: Tuple[float, float, float] = Field(..., description="The target normal vector this pose aims to achieve.")

    @classmethod
    def from_slice_plane(cls, plane: SlicePlane) -> 'LogicalPose':
        """
        Derives a strict logical pose from a validated SlicePlane.
        """
        order_map = {
            RotationConvention.AC_TABLE: "Rz(C) * Rx(A)",
            RotationConvention.BC_TABLE: "Rz(C) * Ry(B)",
            RotationConvention.AB_HEAD: "Rz(B) * Ry(A)"
        }
        
        return cls(
            angles=plane.angle_pair,
            units=plane.angle_units,
            convention=plane.rotation_convention,
            rotation_order=order_map.get(plane.rotation_convention, "UNKNOWN"),
            source_origin=plane.plane_origin,
            source_normal=plane.unit_normal
        )
