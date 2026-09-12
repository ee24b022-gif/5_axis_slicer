import pytest
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from three_axis_gcode import ThreeAxisGCodeGenerator

def test_three_axis_generation():
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=["G0 Z50 F3000"],
        header=["; START"],
        footer=["; END"],
        provenance_enabled=False
    )
    
    generator = ThreeAxisGCodeGenerator(settings, e_multiplier=0.1, travel_threshold=1.5)
    
    path_points = [
        (0.0, 0.0, 0.0), # Start
        (1.0, 0.0, 0.0), # Print move (dist 1.0)
        (10.0, 0.0, 0.0) # Travel move (dist 9.0)
    ]
    
    output = generator.generate(path_points)
    
    # Assert formatting and expected sequence
    assert "; START" in output
    assert "G21 ; Set units to millimeters" in output
    assert "G90 ; Absolute positioning" in output
    assert "G0 Z50 F3000" in output
    
    import re
    
    # Check that there are absolutely no rotary elements (A, B, U, V) with coordinates in the output
    assert not re.search(r'\b[ABUV]-?\d', output)
    
    # Check logic matches expected output
    assert "G0 X0.000 Y0.000 Z0.000 F3000" in output
    assert "G1 X1.000 Y0.000 Z0.000 E0.100 F1500.0" in output
    assert "G1 E-1.900 F2400 ; Retract" in output
    assert "G0 X10.000 Y0.000 Z0.000 F3000 ; Travel" in output
    assert "G1 E0.100 F2400 ; Unretract" in output
    assert "; END" in output
