import pytest
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from rotary_gcode import RotaryGCodeGenerator
from uv_adapter import TableTableUVAdapter

def test_rotary_generation():
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "A", "v": "B"}, # Mapping u -> A and v -> B
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
        provenance_enabled=True
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    generator = RotaryGCodeGenerator(settings, adapter)
    
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0), # Straight up
        (1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    ]
    
    gcode, metadata = generator.generate(path_points)
    
    assert metadata["is_prototype"] is True
    assert metadata["rotary_enabled"] is True
    assert "A" in metadata["axes"]
    assert "B" in metadata["axes"]
    
    assert "G0 X0.000 Y0.000 Z0.000 A0.000 B0.000 F3000" in gcode
    assert "G1 X1.000 Y0.000 Z0.000 A0.000 B0.000 E0.050 F1500.0" in gcode

def test_unverified_mapping_blocks():
    settings = DialectSettings(
        dialect=GCodeDialect.KLIPPER,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        # Missing 'v' mapping completely!
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=[],
        header=[],
        footer=[],
        provenance_enabled=True
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    generator = RotaryGCodeGenerator(settings, adapter)
    
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    ]
    
    with pytest.raises(ValueError, match="Unverified mapping"):
        generator.generate(path_points)
