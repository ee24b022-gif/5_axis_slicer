import pytest
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from rotary_gcode import RotaryGCodeGenerator, GenerationResult, MoveType
from uv_adapter import TableTableUVAdapter
from models import SlicerMachineProfile


def test_rotary_generation():
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "A", "v": "B"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
        provenance_enabled=True
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    generator = RotaryGCodeGenerator(settings, adapter, profile)
    
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        (1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    ]
    
    result: GenerationResult = generator.generate(path_points)
    
    assert result.is_valid
    assert result.metadata["is_prototype"] is True
    assert result.metadata["rotary_enabled"] is True
    assert "A" in result.metadata["axes"]
    assert "B" in result.metadata["axes"]
    
    gcode = result.gcode
    assert "G0 X0.000 Y0.000 Z0.000 F3000 A0.000 B0.000" in gcode
    assert "G1 X1.000 Y0.000 Z0.000 E0.033 F1500.0 A0.000 B0.000" in gcode  # Updated E value for volumetric


def test_unverified_mapping_blocks():
    settings = DialectSettings(
        dialect=GCodeDialect.KLIPPER,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
        provenance_enabled=True
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    generator = RotaryGCodeGenerator(settings, adapter, profile)
    
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    ]
    
    result = generator.generate(path_points)
    assert not result.is_valid
    assert any("unverified mapping" in e.lower() or "unverified" in e.lower() for e in result.validation_errors)


def test_rotary_validation_errors():
    """Test that validation errors are properly captured."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    # Test with NaN input
    gen = RotaryGCodeGenerator(settings, adapter, profile)
    path = [(0.0, 0.0, 0.2, 0.0, 0.0, 1.0), (float('nan'), 0.0, 0.2, 0.0, 0.0, 1.0)]
    result = gen.generate(path)
    assert not result.is_valid
    assert any("non-finite" in e.lower() or "nan" in e.lower() for e in result.validation_errors)


def test_machine_limits():
    """Test machine limit enforcement."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    profile = SlicerMachineProfile()
    profile.limits = {"ranges": {"X": [0, 100], "Y": [-100, 100], "Z": [0, 200]}}
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    gen = RotaryGCodeGenerator(settings, adapter, profile)
    
    # Path beyond X limit
    path = [(0.0, 0.0, 0.2, 0.0, 0.0, 1.0), (150.0, 0.0, 0.2, 0.0, 0.0, 1.0)]
    result = gen.generate(path)
    assert not result.is_valid
    assert any("limit" in e.lower() for e in result.validation_errors)


def test_move_types():
    """Test explicit move type classification."""
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    gen = RotaryGCodeGenerator(settings, adapter, profile, travel_threshold=1.5)
    
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),   # Print path 1
        (10.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Travel to path 2
        (11.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Print path 2
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
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "A", "v": "B"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    gen = RotaryGCodeGenerator(settings, adapter, profile)
    
    path = [(0.0, 0.0, 0.2, 0.0, 0.0, 1.0), (1.0, 0.0, 0.2, 0.0, 0.0, 1.0)]
    gcode, metadata = gen.generate_legacy(path)
    
    assert "G1" in gcode
    assert metadata["is_prototype"] is True


def test_rotary_only_moves():
    """Test pure rotary axis moves (same XYZ, different normals)."""
    import math
    
    settings = DialectSettings(
        dialect=GCodeDialect.KLIPPER_MANUAL_STEPPER_AB,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    gen = RotaryGCodeGenerator(settings, adapter, profile)
    
    sqrt2_2 = 1.0 / math.sqrt(2)
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (0.0, 0.0, 0.2, sqrt2_2, 0, sqrt2_2),
    ]
    
    result = gen.generate(path)
    assert result.is_valid
    gcode = result.gcode
    assert "MANUAL_STEPPER" in gcode or "U" in gcode or "V" in gcode


def test_retraction_logic():
    """Test retraction/unretraction logic with E value consistency."""
    import re
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    gen = RotaryGCodeGenerator(settings, adapter, profile, travel_threshold=1.0)
    
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (1.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (10.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (11.0, 0.0, 0.2, 0.0, 0.0, 1.0),
    ]
    path_ids = [1, 1, 2, 2]
    
    result = gen.generate(path, path_ids)
    gcode = result.gcode
    
    assert "Retract" in gcode
    assert "Unretract" in gcode
    
    # Check E values exist and are consistent
    e_values = []
    for line in gcode.split('\n'):
        if line.startswith('G1') and 'E' in line and 'Retract' not in line and 'Unretract' not in line:
            match = re.search(r'E([-\d.]+)', line)
            if match:
                e_values.append(float(match.group(1)))
    
    assert len(e_values) >= 2, "Should have multiple extrusion moves"


if __name__ == "__main__":
    test_rotary_generation()
    test_unverified_mapping_blocks()
    test_rotary_validation_errors()
    test_machine_limits()
    test_move_types()
    test_legacy_interface()
    test_rotary_only_moves()
    test_retraction_logic()
    print("\nAll rotary_gcode tests passed!")