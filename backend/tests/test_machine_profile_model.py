import pytest
from pydantic import ValidationError
from machine_profile_model import MachineContract, MachineLimits
from enums import RotationConvention

def test_valid_machine_contract():
    contract = MachineContract(
        calibration_revision=1,
        kinematic_convention=RotationConvention.BC_TABLE,
        units="mm",
        axis_names=["X", "Y", "Z", "B", "C"],
        axis_directions={"X": 1, "Y": 1, "Z": 1, "B": -1, "C": 1},
        zero_positions={"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
        table_centers={"X": 150.0, "Y": 150.0},
        command_templates={"linear_move": "G1 X{X} Y{Y} Z{Z} B{B} C{C} F{F}"}
    )
    assert contract.calibration_revision == 1
    assert contract.axis_directions["B"] == -1

def test_missing_axis_in_directions():
    with pytest.raises(ValidationError) as exc:
        MachineContract(
            calibration_revision=1,
            kinematic_convention=RotationConvention.BC_TABLE,
            units="mm",
            axis_names=["X", "Y", "Z", "B", "C"],
            axis_directions={"X": 1, "Y": 1, "Z": 1, "B": -1}, # Missing C
            zero_positions={"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
            command_templates={}
        )
    assert "axis_directions must match axis_names exactly" in str(exc.value)

def test_invalid_axis_direction():
    with pytest.raises(ValidationError) as exc:
        MachineContract(
            calibration_revision=1,
            kinematic_convention=RotationConvention.BC_TABLE,
            units="mm",
            axis_names=["X", "Y", "Z", "B", "C"],
            axis_directions={"X": 1, "Y": 1, "Z": 1, "B": 2, "C": 1}, # Invalid direction 2
            zero_positions={"X": 0.0, "Y": 0.0, "Z": 0.0, "B": 0.0, "C": 0.0},
            command_templates={}
        )
    assert "must be 1 or -1" in str(exc.value)

def test_invalid_limits():
    with pytest.raises(ValidationError) as exc:
        MachineLimits(
            ranges={"X": (300.0, 0.0)} # min > max
        )
    assert "min > max" in str(exc.value)

def test_valid_limits():
    limits = MachineLimits(
        ranges={"X": (0.0, 300.0), "Y": (-10.0, 10.0)}
    )
    assert limits.ranges["X"] == (0.0, 300.0)
