import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from transform_utils import TableTableFractalAdapter
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from rotary_gcode import RotaryGCodeGenerator
from enums import CoordinateMode, GCodeDialect

def test_option1():
    print("Testing TableTableFractalAdapter (Kinematics)...")
    adapter = TableTableFractalAdapter(bed_center_z=0)
    mx, my, mz, rotary = adapter.calculate_ik(10, 10, 10, 0, 1, 0)
    
    assert 'A' in rotary and 'B' in rotary, "Missing A/B rotary axes"
    print(f"IK output: X={mx:.2f}, Y={my:.2f}, Z={mz:.2f}, A={rotary['A']:.2f}, B={rotary['B']:.2f}")

    print("Testing RotaryGCodeGenerator (G-Code)...")
    settings = DialectSettings(
        dialect=GCodeDialect.KLIPPER_MANUAL_STEPPER_AB,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "A": "A", "B": "B"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=1500),
        retraction=RetractionSettings(distance=1.0, feedrate=1500),
        header=["HOME_AB", "Z_TILT_ADJUST", "DIAG_CENTRALIZE"],
        footer=[]
    )
    
    gen = RotaryGCodeGenerator(settings, adapter)
    # Mock toolpath
    pts = [
        (0, 0, 0, 0, 0, 1),
        (10, 10, 10, 0, 1, 0)
    ]
    
    gcode, meta = gen.generate(pts, [1, 1])
    
    assert "HOME_AB" in gcode
    assert "Z_TILT_ADJUST" in gcode
    assert "DIAG_CENTRALIZE" in gcode
    assert "MANUAL_STEPPER STEPPER=stepper_a" in gcode
    assert "MANUAL_STEPPER STEPPER=stepper_b" in gcode
    
    print("All Option 1 Assertions Passed!")
    print(gcode)

if __name__ == "__main__":
    test_option1()
