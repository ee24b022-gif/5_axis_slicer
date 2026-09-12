import pytest
from pose_model import LogicalPose
from enums import AngleUnit, RotationConvention
from fractal_adapter import FractalABAdapter

def get_test_pose(convention: RotationConvention):
    return LogicalPose(
        angles=(45.0, 30.0),
        units=AngleUnit.DEGREES,
        convention=convention,
        rotation_order="dummy",
        source_origin=(0, 0, 0),
        source_normal=(0, 0, 1)
    )

def test_valid_ab_head_mapping():
    contract = {"axis_names": ["X", "Y", "Z", "A", "B"]}
    adapter = FractalABAdapter(contract)
    pose = get_test_pose(RotationConvention.AB_HEAD)
    
    result = adapter.adapt_pose(pose)
    assert result == {"A": 45.0, "B": 30.0}

def test_missing_ab_contract_fails():
    contract = {"axis_names": ["X", "Y", "Z", "U", "V"]}
    with pytest.raises(ValueError, match="Fractal adapter requires explicit A and B axes"):
        FractalABAdapter(contract)

def test_invalid_convention_fails():
    contract = {"axis_names": ["X", "Y", "Z", "A", "B"]}
    adapter = FractalABAdapter(contract)
    
    pose = get_test_pose(RotationConvention.AC_TABLE)
    with pytest.raises(ValueError, match="Fractal adapter cannot safely map AC_TABLE to A/B axes"):
        adapter.adapt_pose(pose)
