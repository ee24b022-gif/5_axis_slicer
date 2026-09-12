import pytest
from pydantic import ValidationError
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings

def test_valid_dialect_initialization():
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=["G0 Z50 F3000"],
        header=["; START"],
        footer=["; END"],
        provenance_enabled=True
    )
    assert settings.dialect == GCodeDialect.MARLIN
    assert settings.feed_limits.travel == 3000

def test_invalid_axis_mapping_fails():
    with pytest.raises(ValidationError, match="Unknown logical axis"):
        DialectSettings(
            dialect=GCodeDialect.KLIPPER,
            axis_mapping={"gamma": "G"},
            feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
            retraction=RetractionSettings(distance=2.0, feedrate=2400)
        )
        
    with pytest.raises(ValidationError, match="Axis mapping target must be a single letter"):
        DialectSettings(
            dialect=GCodeDialect.KLIPPER,
            axis_mapping={"x": "XX"},
            feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
            retraction=RetractionSettings(distance=2.0, feedrate=2400)
        )

def test_feed_limit_bounds():
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        DialectSettings(
            dialect=GCodeDialect.RRF,
            axis_mapping={"x": "X"},
            feed_limits=FeedLimits(travel=-10, print=1500, retract=2400),
            retraction=RetractionSettings(distance=2.0, feedrate=2400)
        )
