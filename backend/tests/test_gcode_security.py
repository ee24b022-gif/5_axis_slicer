import pytest
from pydantic import ValidationError
from enums import GCodeDialect, CoordinateMode
from dialect_model import DialectSettings, FeedLimits, RetractionSettings

def create_base_settings(**kwargs):
    default_args = {
        "dialect": GCodeDialect.MARLIN,
        "coordinate_mode": CoordinateMode.ABSOLUTE,
        "units": "mm",
        "axis_mapping": {"x": "X", "y": "Y", "z": "Z", "e": "E"},
        "feed_limits": FeedLimits(travel=3000, print=1500, retract=2400),
        "retraction": RetractionSettings(distance=2.0, feedrate=2400),
    }
    default_args.update(kwargs)
    return DialectSettings(**default_args)

def test_newline_injection_blocks():
    # Attempting to sneak a fan command past by injecting it after a valid G0 move
    with pytest.raises(ValidationError, match="Newline injection detected"):
        create_base_settings(clearance_moves=["G0 Z50\nM106 S255"])
        
    with pytest.raises(ValidationError, match="Newline injection detected"):
        create_base_settings(header=["G28\rG90"])

def test_unallowlisted_token_blocks():
    # Malicious system command attempting to inject shell execution
    with pytest.raises(ValidationError, match="Malicious or unallowlisted command token detected: 'RM'"):
        create_base_settings(header=["rm -rf /"])
        
    # Valid G-code format, but a destructive token (M502 is Factory Reset)
    with pytest.raises(ValidationError, match="Malicious or unallowlisted command token detected: 'M502'"):
        create_base_settings(footer=["M502"])
        
    # Unrecognized token entirely
    with pytest.raises(ValidationError, match="Malicious or unallowlisted command token detected: 'PRINT'"):
        create_base_settings(header=["PRINT 'Hello'"])

def test_valid_tokens_pass():
    # Should not raise any errors
    settings = create_base_settings(
        header=[
            "; This is a comment",
            "G28 ; Home all axes",
            "M104 S200",
            "M140 S60",
            "G21",
            "G90"
        ],
        clearance_moves=[
            "G0 Z50 F3000",
            "  ; Trailing space comment  "
        ],
        footer=[
            "M107 ; Turn off fan",
            "G1 X0 Y0 F3000"
        ]
    )
    
    assert settings.header[0] == "; This is a comment"
    assert settings.clearance_moves[0] == "G0 Z50 F3000"
    assert settings.footer[0] == "M107 ; Turn off fan"
