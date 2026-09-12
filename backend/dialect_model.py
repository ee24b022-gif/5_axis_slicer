from pydantic import BaseModel, Field, model_validator
from typing import Dict, List
from enums import CoordinateMode, GCodeDialect

class FeedLimits(BaseModel):
    travel: float = Field(..., gt=0, description="Max travel feedrate in mm/min")
    print: float = Field(..., gt=0, description="Max print feedrate in mm/min")
    retract: float = Field(..., gt=0, description="Max retract feedrate in mm/min")

class RetractionSettings(BaseModel):
    distance: float = Field(..., ge=0, description="Retraction distance in mm")
    feedrate: float = Field(..., gt=0, description="Retraction feedrate in mm/min")

class DialectSettings(BaseModel):
    dialect: GCodeDialect
    coordinate_mode: CoordinateMode = CoordinateMode.ABSOLUTE
    units: str = "mm"
    axis_mapping: Dict[str, str] = Field(..., description="Maps logical axes (x, y, z, a, b, u, v, e) to physical machine axes")
    feed_limits: FeedLimits
    retraction: RetractionSettings
    clearance_moves: List[str] = Field(default_factory=list, description="List of pre-print clearance moves")
    header: List[str] = Field(default_factory=list, description="Lines inserted at the top of the G-code")
    footer: List[str] = Field(default_factory=list, description="Lines inserted at the end of the G-code")
    provenance_enabled: bool = True

    @model_validator(mode='after')
    def validate_mapping(self) -> 'DialectSettings':
        allowed_logical = {"x", "y", "z", "a", "b", "c", "u", "v", "w", "e"}
        for k, v in self.axis_mapping.items():
            if k.lower() not in allowed_logical:
                raise ValueError(f"Unknown logical axis: {k}")
            if not v.isalpha() or len(v) != 1:
                raise ValueError(f"Axis mapping target must be a single letter, got '{v}'")
        return self

    @model_validator(mode='after')
    def sanitize_gcode_lines(self) -> 'DialectSettings':
        ALLOWED_GCODE_TOKENS = {
            "G0", "G1", "G2", "G3", "G4", "G10", "G11", "G20", "G21", "G28", "G29", "G90", "G91", "G92",
            "M82", "M83", "M104", "M106", "M107", "M109", "M114", "M117", "M140", "M190", "M220", "M221", "M420",
            "T0", "T1"
        }
        
        for field_name in ['header', 'footer', 'clearance_moves']:
            lines = getattr(self, field_name)
            for raw_line in lines:
                if '\n' in raw_line or '\r' in raw_line:
                    raise ValueError(f"Newline injection detected in {field_name}. Use multiple array items instead.")
                
                line = raw_line.strip()
                if not line or line.startswith(';'):
                    continue
                    
                cmd = line.split()[0].upper()
                if cmd not in ALLOWED_GCODE_TOKENS:
                    raise ValueError(f"Malicious or unallowlisted command token detected: '{cmd}' in {field_name}")
                    
        return self
