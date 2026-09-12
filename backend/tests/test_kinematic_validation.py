import pytest
from validation_service import ValidationService
from slice_plane_model import SlicePlane
from enums import AngleUnit, RotationConvention, DiagnosticStatus, DiagnosticSeverity

def get_test_plane(angle_pair):
    return SlicePlane(
        plane_origin=(0, 0, 10),
        unit_normal=(0, 0, 1),
        angle_pair=angle_pair,
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.BC_TABLE,
        local_x=(1, 0, 0),
        local_y=(0, 1, 0)
    )

def test_missing_implementations():
    plane = get_test_plane((0, 0))
    contract = {"kinematic_convention": "BC_TABLE"}
    limits = {"ranges": {"B": (-90, 90), "C": (-360, 360)}}
    
    res = ValidationService.validate_machine_kinematics(plane, contract, limits)
    
    # Must fail because reachability and singularities are NOT_IMPLEMENTED
    assert res.aggregate_status == DiagnosticStatus.NOT_IMPLEMENTED
    assert res.is_blocking is True
    
    codes = [d.code for d in res.diagnostics]
    assert "SINGULARITY_DETECTION_NOT_IMPLEMENTED" in codes
    assert "REACHABILITY_NOT_IMPLEMENTED" in codes

def test_axis_out_of_range():
    # B is 100, which exceeds limit of 90
    plane = get_test_plane((100, 0))
    contract = {"kinematic_convention": "BC_TABLE"}
    limits = {"ranges": {"B": (-90, 90), "C": (-360, 360)}}
    
    res = ValidationService.validate_machine_kinematics(plane, contract, limits)
    
    # Must fail with OUT_OF_RANGE, which escalates over NOT_IMPLEMENTED
    assert res.aggregate_status == DiagnosticStatus.FAIL
    assert res.is_blocking is True
    
    out_of_range = [d for d in res.diagnostics if d.code == "OUT_OF_RANGE"]
    assert len(out_of_range) == 1
    assert out_of_range[0].details["axis"] == "B"

def test_unmapped_pose():
    plane = get_test_plane((0, 0))
    contract = {"kinematic_convention": "BC_TABLE"}
    # Missing C mapping in limits
    limits = {"ranges": {"B": (-90, 90)}}
    
    res = ValidationService.validate_machine_kinematics(plane, contract, limits)
    
    assert res.aggregate_status == DiagnosticStatus.FAIL
    assert res.is_blocking is True
    
    unmapped = [d for d in res.diagnostics if d.code == "UNMAPPED_POSE"]
    assert len(unmapped) == 1
    assert unmapped[0].details["axis"] == "C"
