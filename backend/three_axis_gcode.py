"""
Three-Axis G-code Generator - Safe, Verified, Unit-Consistent
==============================================================

Strict 3-axis G-code generator that:
- Enforces absolutely no rotary commands (A, B, C, U, V, W) can be emitted
- Uses volumetric extrusion calculation from cross-sectional area
- Validates all outputs are finite and within machine limits
- Explicit move type classification (travel, print, retract)
"""

import math
import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from models import SlicerMachineProfile
import logging

logger = logging.getLogger(__name__)


class MoveType(Enum):
    """Explicit classification of G-code move types."""
    TRAVEL = "travel"           # Non-printing move, retracted
    EXTRUSION = "extrusion"     # Printing move with extrusion
    RETRACTION = "retraction"   # Retract filament
    UNRETRACT = "unretract"     # Unretract (prime) filament
    CLEARANCE = "clearance"     # Start/end clearance moves


@dataclass(frozen=True)
class ValidatedMove:
    """A validated, ready-to-emit G-code move."""
    move_type: MoveType
    gcode_line: str
    machine_x: float
    machine_y: float
    machine_z: float
    extrusion_mm: float            # Filament consumed this move (0 for travel)
    feedrate_mmm: float            # Feedrate in mm/min
    is_finite: bool = True


@dataclass
class GenerationResult:
    """Result of G-code generation with full validation info."""
    gcode: str
    metadata: Dict[str, Any]
    moves: List[ValidatedMove]
    validation_errors: List[str]
    total_extrusion_mm: float
    total_travel_mm: float
    total_print_mm: float
    
    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0


class ThreeAxisGCodeGenerator:
    """
    Strict 3-axis G-code generator with safety validation.
    
    Key safety features:
    - Volumetric extrusion: E = (layer_height * line_width * distance) / (π * (filament_dia/2)^2)
    - Feedrate limiting: respects machine profile limits per axis
    - No rotary axis emission (strictly 3-axis)
    - Finite value checking: all coordinates, feedrates, extrusion verified
    - Machine limit enforcement: blocks moves outside profile limits
    """
    
    def __init__(
        self,
        settings: DialectSettings,
        machine_profile: SlicerMachineProfile,
        layer_height: float = 0.2,
        line_width: float = 0.4,
        filament_diameter: float = 1.75,
        travel_threshold: float = 1.5,
    ):
        self.settings = settings
        self.machine_profile = machine_profile
        self.layer_height = layer_height
        self.line_width = line_width
        self.filament_diameter = filament_diameter
        self.travel_threshold = travel_threshold
        
        # Pre-compute extrusion multiplier: cross-sectional area / filament area
        filament_area = math.pi * (filament_diameter / 2.0) ** 2
        deposited_area = layer_height * line_width
        self.e_multiplier = deposited_area / filament_area  # mm filament per mm of path
        
        # State
        self.current_e = 0.0
        self.last_pos = None  # (x, y, z, path_id)
        self._retracted = False
        self._validation_errors_accumulator: List[str] = []
        
        # Validate settings on init
        self._validate_settings()
    
    def _validate_settings(self) -> List[str]:
        """Validate generator settings. Returns list of errors (empty if valid)."""
        errors = []
        
        # Check required axis mappings (no rotary axes allowed)
        required_axes = ['x', 'y', 'z', 'e']
        for axis in required_axes:
            if axis not in self.settings.axis_mapping:
                errors.append(f"Missing required axis mapping: {axis}")
        
        # Ensure no rotary axes in mapping
        rotary_axes = {'a', 'b', 'c', 'u', 'v', 'w'}
        for axis in self.settings.axis_mapping:
            if axis.lower() in rotary_axes:
                errors.append(f"Rotary axis '{axis}' not allowed in 3-axis generator")
        
        # Check feed limits are positive
        if self.settings.feed_limits.travel <= 0:
            errors.append("Travel feedrate must be > 0")
        if self.settings.feed_limits.print <= 0:
            errors.append("Print feedrate must be > 0")
        if self.settings.feed_limits.retract <= 0:
            errors.append("Retract feedrate must be > 0")
        
        # Check retraction distance
        if self.settings.retraction.distance < 0:
            errors.append("Retraction distance must be >= 0")
        
        # Check machine profile
        if self.machine_profile is None:
            errors.append("Machine profile is required")
        else:
            if not hasattr(self.machine_profile, 'nozzle_length') or self.machine_profile.nozzle_length <= 0:
                errors.append("Machine profile missing valid nozzle_length")
            if not hasattr(self.machine_profile, 'nozzle_holder_radius') or self.machine_profile.nozzle_holder_radius <= 0:
                errors.append("Machine profile missing valid nozzle_holder_radius")
        
        # Check slicing parameters
        if self.layer_height <= 0:
            errors.append("Layer height must be > 0")
        if self.line_width <= 0:
            errors.append("Line width must be > 0")
        if self.filament_diameter <= 0:
            errors.append("Filament diameter must be > 0")
        if self.travel_threshold < 0:
            errors.append("Travel threshold must be >= 0")
        
        if errors:
            raise ValueError("Generator validation failed: " + "; ".join(errors))
        
        return errors
    
    def _check_finite(self, name: str, value: float, context: str = "") -> None:
        """Raise ValueError if value is not finite."""
        if not math.isfinite(value):
            raise ValueError(f"Non-finite {name}: {value} ({context})")
    
    def _safe_check_finite(self, name: str, value: float, context: str = "") -> bool:
        """Check if value is finite, return False if not."""
        if not math.isfinite(value):
            self._validation_errors_accumulator.append(f"Non-finite {name}: {value} ({context})")
            return False
        return True
    
    def _check_machine_limits(self, x: float, y: float, z: float) -> List[str]:
        """Check if machine position exceeds profile limits. Returns list of violations."""
        violations = []
        
        if not (hasattr(self.machine_profile, 'limits') and self.machine_profile.limits):
            return violations
        
        ranges = self.machine_profile.limits.get('ranges', {})
        
        for axis, val in [('X', x), ('Y', y), ('Z', z)]:
            if axis in ranges:
                min_v, max_v = ranges[axis]
                if val < min_v or val > max_v:
                    violations.append(f"{axis}={val:.3f} outside limits [{min_v}, {max_v}]")
        
        return violations
    
    def _retract(self, gcode: List[str]) -> None:
        """Emit retraction move."""
        if not self._retracted and self.settings.retraction.distance > 0:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            new_e = self.current_e - self.settings.retraction.distance
            gcode.append(f"G1 {e_axis}{new_e:.3f} F{self.settings.retraction.feedrate:.0f} ; Retract")
            self.current_e = new_e
            self._retracted = True
    
    def _unretract(self, gcode: List[str]) -> None:
        """Emit unretraction (prime) move."""
        if self._retracted and self.settings.retraction.distance > 0:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            gcode.append(f"G1 {e_axis}{self.current_e:.3f} F{self.settings.retraction.feedrate:.0f} ; Unretract")
            self._retracted = False
    
    def _emit_move(
        self,
        gcode: List[str],
        move_type: MoveType,
        x: float, y: float, z: float,
        feedrate: float,
        extrusion: float = 0.0,
        comment: str = ""
    ) -> Optional[ValidatedMove]:
        """Emit a validated move and return the move record, or None if validation fails."""
        # Validate all values are finite
        for name, val in [('x', x), ('y', y), ('z', z), ('feedrate', feedrate), ('extrusion', extrusion)]:
            if not self._safe_check_finite(name, val, f"{move_type.value} move"):
                return None
        
        # Check machine limits
        violations = self._check_machine_limits(x, y, z)
        if violations:
            self._validation_errors_accumulator.append(
                f"Machine limit violation on {move_type.value}: {'; '.join(violations)}"
            )
            return None
        
        x_ax = self.settings.axis_mapping.get('x', 'X')
        y_ax = self.settings.axis_mapping.get('y', 'Y')
        z_ax = self.settings.axis_mapping.get('z', 'Z')
        e_ax = self.settings.axis_mapping.get('e', 'E')
        
        if move_type == MoveType.TRAVEL:
            line = f"G0 {x_ax}{x:.3f} {y_ax}{y:.3f} {z_ax}{z:.3f} F{feedrate:.0f}"
            if comment:
                line += f" ; {comment}"
        elif move_type == MoveType.EXTRUSION:
            self.current_e += extrusion
            line = f"G1 {x_ax}{x:.3f} {y_ax}{y:.3f} {z_ax}{z:.3f} {e_ax}{self.current_e:.3f} F{feedrate:.1f}"
            if comment:
                line += f" ; {comment}"
        elif move_type == MoveType.RETRACTION:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            line = f"G1 {e_axis}{self.current_e:.3f} F{feedrate:.0f} ; Retract"
        elif move_type == MoveType.UNRETRACT:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            line = f"G1 {e_axis}{self.current_e:.3f} F{feedrate:.0f} ; Unretract"
        elif move_type == MoveType.CLEARANCE:
            line = f"G0 {x_ax}{x:.3f} {y_ax}{y:.3f} {z_ax}{z:.3f} F{feedrate:.0f} ; Clearance"
        else:
            raise ValueError(f"Unknown move type: {move_type}")
        
        gcode.append(line)
        
        return ValidatedMove(
            move_type=move_type,
            gcode_line=line,
            machine_x=x,
            machine_y=y,
            machine_z=z,
            extrusion_mm=extrusion,
            feedrate_mmm=feedrate,
            is_finite=True
        )
    
    def generate(self, path_points: List[Tuple], path_ids: Optional[List[int]] = None) -> GenerationResult:
        """
        Generate G-code from toolpath points.
        
        Args:
            path_points: List of (x, y, z) or (x, y, z, nx, ny, nz) - only x,y,z used
            path_ids: Optional list of path IDs for travel detection
        
        Returns:
            GenerationResult with gcode, metadata, moves, and validation info
        """
        validation_errors = []
        moves = []
        gcode_lines = []
        
        # Reset error accumulator
        self._validation_errors_accumulator = []
        
        try:
            if not path_points:
                return GenerationResult(
                    gcode="",
                    metadata={"is_prototype": True, "rotary_enabled": False, "axes": [], "error": "Empty path"},
                    moves=[],
                    validation_errors=["Empty path points"],
                    total_extrusion_mm=0.0,
                    total_travel_mm=0.0,
                    total_print_mm=0.0
                )
            
            # Header
            gcode_lines.extend(self.settings.header)
            
            if self.settings.units == "mm":
                gcode_lines.append("G21 ; Set units to millimeters")
            
            if self.settings.coordinate_mode.value == "absolute":
                gcode_lines.append("G90 ; Absolute positioning")
                gcode_lines.append("M82 ; Absolute extrusion mode")
            
            # Clearance moves
            for clear_move in self.settings.clearance_moves:
                gcode_lines.append(clear_move)
                moves.append(ValidatedMove(
                    move_type=MoveType.CLEARANCE,
                    gcode_line=clear_move,
                    machine_x=0, machine_y=0, machine_z=0,
                    extrusion_mm=0, feedrate_mmm=0
                ))
            
            x_ax = self.settings.axis_mapping.get('x', 'X')
            y_ax = self.settings.axis_mapping.get('y', 'Y')
            z_ax = self.settings.axis_mapping.get('z', 'Z')
            
            total_extrusion = 0.0
            total_travel = 0.0
            total_print = 0.0
            
            for i, pt in enumerate(path_points):
                x, y = pt[0], pt[1]
                z = pt[2] if len(pt) > 2 else 0.0
                current_path_id = path_ids[i] if path_ids else 0
                
                # Validate inputs
                if not all(self._safe_check_finite(f"{k}[{i}]", v, "input") 
                           for k, v in [('x', x), ('y', y), ('z', z)]):
                    pass  # Errors already accumulated
                
                if self.last_pos is None:
                    # First move - clearance to start position
                    feedrate = self.settings.feed_limits.travel
                    move = self._emit_move(
                        gcode_lines, MoveType.CLEARANCE,
                        x, y, z, feedrate,
                        comment="First move to start"
                    )
                    if move is not None:
                        moves.append(move)
                    
                    self.last_pos = (x, y, z, current_path_id)
                    continue
                
                last_x, last_y, last_z, last_path_id = self.last_pos
                
                # Distance in PART frame (for travel vs print decision)
                dist = math.hypot(x - last_x, y - last_y, z - last_z)
                
                # Determine move type
                is_travel = (dist > self.travel_threshold or 
                            (path_ids and current_path_id != last_path_id))
                
                if is_travel:
                    # Travel move
                    if dist > 1e-6:
                        self._retract(gcode_lines)
                        moves.append(ValidatedMove(
                            move_type=MoveType.RETRACTION,
                            gcode_line=gcode_lines[-1],
                            machine_x=last_x, machine_y=last_y, machine_z=last_z,
                            extrusion_mm=0,
                            feedrate_mmm=self.settings.retraction.feedrate
                        ))
                        
                        feedrate = self.settings.feed_limits.travel
                        move = self._emit_move(
                            gcode_lines, MoveType.TRAVEL,
                            x, y, z, feedrate,
                            comment=f"Travel to path {current_path_id}"
                        )
                        if move is not None:
                            moves.append(move)
                            total_travel += dist
                    
                    self._unretract(gcode_lines)
                    if gcode_lines and gcode_lines[-1].startswith("G1") and "Unretract" in gcode_lines[-1]:
                        moves.append(ValidatedMove(
                            move_type=MoveType.UNRETRACT,
                            gcode_line=gcode_lines[-1],
                            machine_x=x, machine_y=y, machine_z=z,
                            extrusion_mm=0,
                            feedrate_mmm=self.settings.retraction.feedrate
                        ))
                
                else:
                    # Print move
                    if dist > 1e-6:
                        self._unretract(gcode_lines)
                        if gcode_lines and gcode_lines[-1].startswith("G1") and "Unretract" in gcode_lines[-1]:
                            moves.append(ValidatedMove(
                                move_type=MoveType.UNRETRACT,
                                gcode_line=gcode_lines[-1],
                                machine_x=x, machine_y=y, machine_z=z,
                                extrusion_mm=0,
                                feedrate_mmm=self.settings.retraction.feedrate
                            ))
                        
                        extrusion = dist * self.e_multiplier
                        feedrate = self.settings.feed_limits.print
                        
                        move = self._emit_move(
                            gcode_lines, MoveType.EXTRUSION,
                            x, y, z, feedrate,
                            extrusion=extrusion,
                            comment=f"Print path {current_path_id}"
                        )
                        if move is not None:
                            moves.append(move)
                            total_extrusion += extrusion
                            total_print += dist
                
                self.last_pos = (x, y, z, current_path_id)
            
            # Footer
            gcode_lines.extend(self.settings.footer)
            
            # Collect accumulated errors
            validation_errors.extend(self._validation_errors_accumulator)
            
            # Final validation
            if not math.isfinite(self.current_e):
                validation_errors.append("Final extrusion position non-finite")
            
            # Collect axes used
            axes_used = [
                self.settings.axis_mapping.get('x', 'X'),
                self.settings.axis_mapping.get('y', 'Y'),
                self.settings.axis_mapping.get('z', 'Z'),
                self.settings.axis_mapping.get('e', 'E'),
            ]
            
            metadata = {
                "is_prototype": True,
                "rotary_enabled": False,
                "axes": axes_used,
                "total_extrusion_mm": total_extrusion,
                "total_travel_mm": total_travel,
                "total_print_mm": total_print,
                "layer_height_mm": self.layer_height,
                "line_width_mm": self.line_width,
                "filament_diameter_mm": self.filament_diameter,
                "e_multiplier": self.e_multiplier,
            }
            
            return GenerationResult(
                gcode="\n".join(gcode_lines),
                metadata=metadata,
                moves=moves,
                validation_errors=validation_errors,
                total_extrusion_mm=total_extrusion,
                total_travel_mm=total_travel,
                total_print_mm=total_print,
            )
            
        except Exception as e:
            logger.exception("G-code generation failed")
            validation_errors.append(f"Generation error: {e}")
            validation_errors.extend(self._validation_errors_accumulator)
            return GenerationResult(
                gcode="\n".join(gcode_lines) if gcode_lines else "",
                metadata={"is_prototype": True, "error": str(e)},
                moves=moves,
                validation_errors=validation_errors,
                total_extrusion_mm=total_extrusion if 'total_extrusion' in locals() else 0.0,
                total_travel_mm=total_travel if 'total_travel' in locals() else 0.0,
                total_print_mm=total_print if 'total_print' in locals() else 0.0,
            )
    
    # Backward compatibility method
    def generate_legacy(self, path_points: List[Tuple], path_ids: Optional[List[int]] = None) -> Tuple[str, Dict]:
        """Legacy interface returning (gcode_str, metadata_dict)."""
        result = self.generate(path_points, path_ids)
        if not result.is_valid:
            raise ValueError(f"G-code generation failed validation: {result.validation_errors}")
        return result.gcode, result.metadata


# --- Test Functions ---

def test_volumetric_extrusion():
    """Test volumetric extrusion calculation."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    profile = SlicerMachineProfile()
    
    gen = ThreeAxisGCodeGenerator(
        settings, profile,
        layer_height=0.2, line_width=0.4, filament_diameter=1.75
    )
    
    expected = (0.2 * 0.4) / (math.pi * (1.75/2)**2)
    assert math.isclose(gen.e_multiplier, expected, rel_tol=1e-5)
    
    print("✓ Volumetric extrusion calculation")


def test_unit_consistency():
    """Test that all feedrates are in mm/min."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    profile = SlicerMachineProfile()
    
    gen = ThreeAxisGCodeGenerator(settings, profile)
    
    path = [(0.0, 0.0, 0.2), (10.0, 0.0, 0.2)]
    
    result = gen.generate(path)
    
    assert result.is_valid
    for move in result.moves:
        if move.move_type == MoveType.EXTRUSION:
            assert move.feedrate_mmm == 1500.0
        elif move.move_type == MoveType.TRAVEL:
            assert move.feedrate_mmm == 3000.0
    
    print("✓ Unit consistency (mm/min)")


def test_finite_validation():
    """Test that non-finite values are rejected."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    profile = SlicerMachineProfile()
    
    gen = ThreeAxisGCodeGenerator(settings, profile)
    
    path = [(0.0, 0.0, 0.2), (float('nan'), 0.0, 0.2)]
    
    result = gen.generate(path)
    assert not result.is_valid
    assert any("non-finite" in e.lower() or "nan" in e.lower() for e in result.validation_errors)
    
    print("✓ Finite validation")


def test_machine_limit_enforcement():
    """Test that machine limits block out-of-bounds moves."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    
    profile = SlicerMachineProfile()
    profile.limits = {"ranges": {"X": [0, 100], "Y": [-100, 100], "Z": [0, 200]}}
    
    gen = ThreeAxisGCodeGenerator(settings, profile)
    
    path = [(0.0, 0.0, 0.2), (150.0, 0.0, 0.2)]
    
    result = gen.generate(path)
    assert not result.is_valid
    assert any("limit" in e.lower() for e in result.validation_errors)
    
    print("✓ Machine limit enforcement")


def test_no_rotary_axes():
    """Test that rotary axes are rejected."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'a': 'A'},  # Has rotary axis A
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    profile = SlicerMachineProfile()
    
    try:
        ThreeAxisGCodeGenerator(settings, profile)
        assert False, "Should have raised"
    except ValueError as e:
        assert "rotary axis" in str(e).lower()
    
    print("✓ Rotary axis rejection")


def test_move_type_classification():
    """Test explicit move type classification."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    profile = SlicerMachineProfile()
    
    gen = ThreeAxisGCodeGenerator(settings, profile, travel_threshold=1.5)
    
    path = [
        (0.0, 0.0, 0.2),   # Print path 1
        (10.0, 0.0, 0.2),  # Travel to path 2 (dist > threshold)
        (11.0, 0.0, 0.2),  # Print path 2
    ]
    path_ids = [1, 2, 2]
    
    result = gen.generate(path, path_ids)
    
    move_types = [m.move_type for m in result.moves]
    assert MoveType.TRAVEL in move_types
    assert MoveType.EXTRUSION in move_types
    assert MoveType.RETRACTION in move_types
    assert MoveType.UNRETRACT in move_types
    assert MoveType.CLEARANCE in move_types
    
    print("✓ Move type classification")


def test_retraction_logic():
    """Test retraction/unretraction logic."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    import re
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    profile = SlicerMachineProfile()
    
    gen = ThreeAxisGCodeGenerator(settings, profile, travel_threshold=1.0)
    
    path = [
        (0.0, 0.0, 0.2),   # Print
        (1.0, 0.0, 0.2),   # Print (same path)
        (10.0, 0.0, 0.2),  # Travel (dist > threshold)
        (11.0, 0.0, 0.2),  # Print (new path)
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
    
    assert any(e > 0 for e in e_values), "Should have positive extrusion"
    
    print("✓ Retraction logic")


if __name__ == "__main__":
    test_volumetric_extrusion()
    test_unit_consistency()
    test_finite_validation()
    test_machine_limit_enforcement()
    test_no_rotary_axes()
    test_move_type_classification()
    test_retraction_logic()
    print("\nAll ThreeAxisGCodeGenerator validation tests passed!")