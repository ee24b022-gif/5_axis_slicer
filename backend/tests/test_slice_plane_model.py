import pytest
import math
from pydantic import ValidationError
from slice_plane_model import SlicePlane
from enums import AngleUnit, RotationConvention

def test_valid_slice_plane():
    # Construct an orthogonal, unit-length plane
    plane = SlicePlane(
        plane_origin=(10.0, 10.0, 5.0),
        unit_normal=(0.0, 0.0, 1.0),
        angle_pair=(45.0, 90.0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=(1.0, 0.0, 0.0),
        local_y=(0.0, 1.0, 0.0),
        source_frame="canonical"
    )
    
    assert plane.unit_normal == (0.0, 0.0, 1.0)
    assert plane.rotation_convention == RotationConvention.AC_TABLE
    assert plane.angle_units == AngleUnit.DEGREES

def test_invalid_normal_rejected():
    with pytest.raises(ValidationError) as exc:
        SlicePlane(
            plane_origin=(0.0, 0.0, 0.0),
            unit_normal=(0.0, 0.0, 2.0), # Non-unit normal
            angle_pair=(0.0, 0.0),
            angle_units=AngleUnit.DEGREES,
            rotation_convention=RotationConvention.AC_TABLE,
            local_x=(1.0, 0.0, 0.0),
            local_y=(0.0, 1.0, 0.0)
        )
    assert "Normal vector must be a unit vector" in str(exc.value)

def test_non_orthogonal_axes_rejected():
    with pytest.raises(ValidationError) as exc:
        SlicePlane(
            plane_origin=(0.0, 0.0, 0.0),
            unit_normal=(0.0, 0.0, 1.0),
            angle_pair=(0.0, 0.0),
            angle_units=AngleUnit.DEGREES,
            rotation_convention=RotationConvention.AC_TABLE,
            # local_x is not orthogonal to local_y
            local_x=(math.sqrt(2)/2, math.sqrt(2)/2, 0.0),
            local_y=(1.0, 0.0, 0.0)
        )
    assert "Local X and Y axes are not orthogonal" in str(exc.value)

def test_invalid_angle_ranges():
    with pytest.raises(ValidationError) as exc:
        SlicePlane(
            plane_origin=(0.0, 0.0, 0.0),
            unit_normal=(0.0, 0.0, 1.0),
            angle_pair=(400.0, 0.0), # Exceeds +/- 360 limit
            angle_units=AngleUnit.DEGREES,
            rotation_convention=RotationConvention.AC_TABLE,
            local_x=(1.0, 0.0, 0.0),
            local_y=(0.0, 1.0, 0.0)
        )
    assert "exceeds valid mechanical rotational bounds" in str(exc.value)

def test_unsupported_conventions():
    with pytest.raises(ValidationError) as exc:
        SlicePlane(
            plane_origin=(0.0, 0.0, 0.0),
            unit_normal=(0.0, 0.0, 1.0),
            angle_pair=(0.0, 0.0),
            angle_units=AngleUnit.DEGREES,
            rotation_convention="MAGIC_HEAD", # Invalid convention
            local_x=(1.0, 0.0, 0.0),
            local_y=(0.0, 1.0, 0.0)
        )
    assert "Input should be 'AC_TABLE', 'BC_TABLE' or 'AB_HEAD'" in str(exc.value)
