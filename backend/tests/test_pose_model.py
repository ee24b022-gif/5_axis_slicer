import pytest
from pydantic import ValidationError
from slice_plane_model import SlicePlane
from pose_model import LogicalPose
from enums import AngleUnit, RotationConvention

def test_logical_pose_creation():
    plane = SlicePlane(
        plane_origin=(10.0, 20.0, 30.0),
        unit_normal=(0.0, 0.0, 1.0),
        angle_pair=(45.0, -45.0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.BC_TABLE,
        local_x=(1.0, 0.0, 0.0),
        local_y=(0.0, 1.0, 0.0)
    )

    pose = LogicalPose.from_slice_plane(plane)
    
    assert pose.angles == (45.0, -45.0)
    assert pose.units == AngleUnit.DEGREES
    assert pose.convention == RotationConvention.BC_TABLE
    assert pose.rotation_order == "Rz(C) * Ry(B)"
    assert pose.source_origin == (10.0, 20.0, 30.0)
    assert pose.source_normal == (0.0, 0.0, 1.0)

def test_logical_pose_immutability():
    # Should raise validation error if instantiated directly with wrong types/lengths
    with pytest.raises(ValidationError):
        LogicalPose(
            angles=(45.0,), # wrong length tuple
            units=AngleUnit.DEGREES,
            convention=RotationConvention.BC_TABLE,
            rotation_order="Rz(C) * Ry(B)",
            source_origin=(10.0, 20.0, 30.0),
            source_normal=(0.0, 0.0, 1.0)
        )
