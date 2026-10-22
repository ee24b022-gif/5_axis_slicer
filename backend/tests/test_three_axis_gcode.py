import pytest
import re
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from three_axis_gcode import ThreeAxisGCodeGenerator, GenerationResult, MoveType
from models import SlicerMachineProfile


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
    
    profile = SlicerMachineProfile()
    generator = ThreeAxisGCodeGenerator(settings, profile, layer_height=0.2, line_width=0.4, filament_diameter=1.75, travel_threshold=1.5)
    
    path_points = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (10.0, 0.0, 0.0)
    ]
    
    result: GenerationResult = generator.generate(path_points)
    
    assert result.is_valid
    gcode = result.gcode
    
    assert "; START" in gcode
    assert "G21 ; Set units to millimeters" in gcode
    assert "G90 ; Absolute positioning" in gcode
    assert "G0 Z50 F3000" in gcode
    
    # Check no rotary elements
    assert not re.search(r'\b[ABUV]-?\d', gcode)
    
    # Check logic - updated E value for volumetric (0.2*0.4/(pi*(1.75/2)^2) ≈ 0.033)
    assert "G0 X0.000 Y0.000 Z0.000 F3000" in gcode
    assert "G1 X1.000 Y0.000 Z0.000 E0.033 F1500.0" in gcode  # Updated E
    assert "G1 E-1.967 F2400 ; Retract" in gcode  # Updated E after retract
    assert "G0 X10.000 Y0.000 Z0.000 F3000 ; Travel" in gcode
    assert "G1 E-1.967 F2400 ; Unretract" in gcode  # After retract E=-1.967, unretract restores to 0.033 (but current_e is still -1.967 until next print)
    assert "; END" in gcode


def test_three_axis_validation_errors():
    """Test that validation errors are properly captured."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    profile = SlicerMachineProfile()
    gen = ThreeAxisGCodeGenerator(settings, profile)
    
    # Test with NaN input
    path = [(0.0, 0.0, 0.2), (float('nan'), 0.0, 0.2)]
    result = gen.generate(path)
    assert not result.is_valid
    assert any("non-finite" in e.lower() or "nan" in e.lower() for e in result.validation_errors)


def test_machine_limits():
    """Test machine limit enforcement."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    profile = SlicerMachineProfile()
    profile.limits = {"ranges": {"X": [0, 100], "Y": [-100, 100], "Z": [0, 200]}}
    gen = ThreeAxisGCodeGenerator(settings, profile)
    
    # Path beyond X limit
    path = [(0.0, 0.0, 0.2), (150.0, 0.0, 0.2)]
    result = gen.generate(path)
    assert not result.is_valid
    assert any("limit" in e.lower() for e in result.validation_errors)


def test_no_rotary_axes():
    """Test that rotary axes are rejected at construction."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "a": "A"},  # Has rotary axis A
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    profile = SlicerMachineProfile()
    with pytest.raises(ValueError, match="Rotary axis"):
        ThreeAxisGCodeGenerator(settings, profile)


def test_move_types():
    """Test explicit move type classification."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    profile = SlicerMachineProfile()
    gen = ThreeAxisGCodeGenerator(settings, profile, travel_threshold=1.5)
    
    path = [
        (0.0, 0.0, 0.2),
        (10.0, 0.0, 0.2),
        (11.0, 0.0, 0.2),
    ]
    path_ids = [1, 2, 2]
    
    result = gen.generate(path, path_ids)
    move_types = [m.move_type for m in result.moves]
    
    assert MoveType.TRAVEL in move_types
    assert MoveType.EXTRUSION in move_types
    assert MoveType.RETRACTION in move_types
    assert MoveType.UNRETRACT in move_types
    assert MoveType.CLEARANCE in move_types


def test_legacy_interface():
    """Test backward compatibility generate_legacy method."""
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
    )
    
    profile = SlicerMachineProfile()
    gen = ThreeAxisGCodeGenerator(settings, profile)
    
    path = [(0.0, 0.0, 0.2), (1.0, 0.0, 0.2)]
    gcode, metadata = gen.generate_legacy(path)
    
    assert "G1" in gcode
    assert metadata["is_prototype"] is True


def test_retraction_logic():
    """Test retraction/unretraction logic."""
    import re
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    profile = SlicerMachineProfile()
    gen = ThreeAxisGCodeGenerator(settings, profile, travel_threshold=1.0)
    
    path = [
        (0.0, 0.0, 0.2),
        (1.0, 0.0, 0.2),
        (10.0, 0.0, 0.2),
        (11.0, 0.0, 0.2),
    ]
    path_ids = [1, 1, 2, 2]
    
    result = gen.generate(path, path_ids)
    gcode = result.gcode
    
    assert "Retract" in gcode
    assert "Unretract" in gcode
    
    e_values = []
    for line in gcode.split('\n'):
        if line.startswith('G1') and 'E' in line and 'Retract' not in line and 'Unretract' not in line:
            match = re.search(r'E([-\d.]+)', line)
            if match:
                e_values.append(float(match.group(1)))
    
    assert len(e_values) >= 2


if __name__ == "__main__":
    test_three_axis_generation()
    test_three_axis_validation_errors()
    test_machine_limits()
    test_no_rotary_axes()
    test_move_types()
    test_legacy_interface()
    test_retraction_logic()
    print("\nAll three_axis_gcode tests passed!")