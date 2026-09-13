import pytest
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from three_axis_gcode import ThreeAxisGCodeGenerator
from rotary_gcode import RotaryGCodeGenerator
from uv_adapter import TableTableUVAdapter
from uuid import UUID
from datetime import datetime, timezone
import math

INV_SQRT2 = math.sqrt(2) / 2

@pytest.fixture
def base_settings():
    return DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=["G0 Z50 F3000"],
        header=["; START", "; Job ID: 12345678-1234-5678-1234-567812345678", "; Profile: Test Slicer", "; Timestamp: 2025-01-01T12:00:00+00:00"],
        footer=["; END"],
        provenance_enabled=True
    )

def test_three_axis_snapshot(snapshot, base_settings):
    # Fix job details for deterministic snapshots
    generator = ThreeAxisGCodeGenerator(base_settings, e_multiplier=0.1, travel_threshold=1.5)
    
    path_points = [
        (0.0, 0.0, 0.0), # Start
        (1.0, 0.0, 0.0), # Print move (dist 1.0)
        (10.0, 0.0, 0.0) # Travel move (dist 9.0)
    ]
    
    output = generator.generate(path_points)
    
    assert output == snapshot

def test_klipper_rotary_axis_ab_snapshot(snapshot, base_settings):
    settings = base_settings.model_copy()
    settings.dialect = GCodeDialect.KLIPPER
    settings.axis_mapping = {"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "A", "v": "B"}
    
    settings.header = ["; START", "; Profile: Klipper Prototype AB", "; Timestamp: 2025-01-01T12:00:00+00:00"]
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    generator = RotaryGCodeGenerator(settings, adapter)
    
    # Simulate a path requiring both U/V movement (which is mapped to A/B)
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0), 
        (1.0, 0.0, 0.0, INV_SQRT2, 0.0, INV_SQRT2), # Roughly 45 degree tilt
        (1.0, 1.0, 0.0, 0.0, INV_SQRT2, INV_SQRT2)  # Another tilt
    ]
    
    gcode, metadata = generator.generate(path_points)
    assert gcode == snapshot
    
    # Assert metadata provenance is correct
    assert metadata["is_prototype"] is True
    assert "A" in metadata["axes"]

def test_klipper_manual_stepper_ab_snapshot(snapshot, base_settings):
    settings = base_settings.model_copy()
    settings.dialect = GCodeDialect.KLIPPER_MANUAL_STEPPER_AB
    # Manual stepper uses U/V mapping dynamically in the generator, but we define them here to pass verify_mapping
    settings.axis_mapping = {"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "stepper_a", "v": "stepper_b"}
    
    settings.header = ["; START", "; Profile: Klipper Manual Stepper AB", "; Timestamp: 2025-01-01T12:00:00+00:00"]
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    generator = RotaryGCodeGenerator(settings, adapter)
    
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        (10.0, 10.0, 0.0, INV_SQRT2, 0.0, INV_SQRT2)
    ]
    
    gcode, metadata = generator.generate(path_points)
    assert gcode == snapshot

def test_rotary_rejected_mapping():
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        # Missing 'v' mapping completely!
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "A"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    
    adapter = TableTableUVAdapter(bed_center_z=0.0)
    generator = RotaryGCodeGenerator(settings, adapter)
    
    path_points = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    ]
    
    with pytest.raises(ValueError, match="Unverified mapping"):
        generator.generate(path_points)
