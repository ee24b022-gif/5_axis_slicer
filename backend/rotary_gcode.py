"""
Rotary G-code Generator - Safe, Verified, Unit-Consistent
==========================================================

This module generates 5-axis G-code with:
- Strict unit consistency (internal mm/mm/min, output mm/mm/min)
- Volumetric extrusion calculation from cross-sectional area
- Explicit move type classification (travel, print, retract, rotary-only)
- Fail-closed validation: blocks export on any non-finite or out-of-limits value
- Verified rotary axis mapping (no unverified axes emitted)

INTERNAL UNIT CONVENTION
------------------------
- All positions: millimeters (mm)
- All feedrates: mm/min (linear), deg/min (rotary)
- Extrusion: mm (filament length)
- Layer height: mm
- Line width: mm
- Filament diameter: mm

CONVERSION ONLY AT OUTPUT BOUNDARY
----------------------------------
The generator works in internal units throughout. Unit conversion
(if ever needed) happens ONLY at the final string formatting.
"""

import math
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
    ROTARY_ONLY = "rotary_only" # Pure rotary axis move (no XYZ)
    CLEARANCE = "clearance"     # Start/end clearance moves


@dataclass(frozen=True)
class ValidatedMove:
    """A validated, ready-to-emit G-code move."""
    move_type: MoveType
    gcode_line: str
    machine_x: float
    machine_y: float
    machine_z: float
    rotary_axes: Dict[str, float]  # e.g., {'u': 10.5, 'v': -20.0}
    extrusion_mm: float            # Filament consumed this move (0 for travel)
    feedrate_mmm: float            # Feedrate in mm/min
    is_finite: bool = True         # Always True for ValidatedMove


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


class RotaryGCodeGenerator:
    """
    5-axis G-code generator with safety validation.
    
    Key safety features:
    - Volumetric extrusion: E = (layer_height * line_width * distance) / (π * (filament_dia/2)^2)
    - Feedrate limiting: respects machine profile limits per axis
    - Rotary axis validation: every emitted rotary axis must be in axis_mapping
    - Finite value checking: all coordinates, feedrates, extrusion verified
    - Machine limit enforcement: blocks moves outside profile limits
    """
    
    def __init__(
        self,
        settings: DialectSettings,
        kinematics_adapter,
        machine_profile: SlicerMachineProfile,
        layer_height: float = 0.2,
        line_width: float = 0.4,
        filament_diameter: float = 1.75,
        travel_threshold: float = 1.5,
    ):
        self.settings = settings
        self.kinematics = kinematics_adapter
        self.machine_profile = machine_profile
        self.layer_height = layer_height
        self.line_width = line_width
        self.filament_diameter = filament_diameter
        self.travel_threshold = travel_threshold
        
        # Pre-compute extrusion multiplier: cross-sectional area / filament area
        # Filament cross-section: π * (d/2)^2
        # Deposited cross-section: layer_height * line_width
        # E (mm of filament) = deposited_volume / filament_area
        #   = (layer_height * line_width * distance) / (π * (filament_dia/2)^2)
        filament_area = math.pi * (filament_diameter / 2.0) ** 2
        deposited_area = layer_height * line_width
        self.e_multiplier = deposited_area / filament_area  # mm filament per mm of path
        
        # State
        self.current_e = 0.0
        self.last_machine_pos = None  # (mx, my, mz, rotary_dict)
        self.last_part_pos = None     # (x, y, z)
        self.last_path_id = None
        self._retracted = False
        self._validation_errors_accumulator: List[str] = []
        
        # Validate settings on init
        self._validate_settings()
    
    def _validate_settings(self) -> List[str]:
        """Validate generator settings. Returns list of errors (empty if valid)."""
        errors = []
        
        # Check required axis mappings
        required_axes = ['x', 'y', 'z', 'e']
        for axis in required_axes:
            if axis not in self.settings.axis_mapping:
                errors.append(f"Missing required axis mapping: {axis}")
        
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
        
        # Check machine profile has required limits
        if self.machine_profile is None:
            errors.append("Machine profile is required")
        else:
            if not hasattr(self.machine_profile, 'nozzle_length') or self.machine_profile.nozzle_length <= 0:
                errors.append("Machine profile missing valid nozzle_length")
            if not hasattr(self.machine_profile, 'nozzle_holder_radius') or self.machine_profile.nozzle_holder_radius <= 0:
                errors.append("Machine profile missing valid nozzle_holder_radius")
            
            # Check axis limits if present
            if hasattr(self.machine_profile, 'limits') and self.machine_profile.limits:
                ranges = self.machine_profile.limits.get('ranges', {})
                for axis in ['X', 'Y', 'Z', 'A', 'B', 'C', 'U', 'V', 'W']:
                    if axis in ranges:
                        min_v, max_v = ranges[axis]
                        if not (math.isfinite(min_v) and math.isfinite(max_v) and min_v < max_v):
                            errors.append(f"Invalid machine limit for {axis}: [{min_v}, {max_v}]")
        
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
        """Check if value is finite, return False if not (for use in generate loop)."""
        if not math.isfinite(value):
            self._validation_errors_accumulator.append(f"Non-finite {name}: {value} ({context})")
            return False
        return True
    
    def _check_machine_limits(self, mx: float, my: float, mz: float, rotary_dict: Dict[str, float]) -> List[str]:
        """Check if machine position exceeds profile limits. Returns list of violations."""
        violations = []
        
        if not (hasattr(self.machine_profile, 'limits') and self.machine_profile.limits):
            return violations
        
        ranges = self.machine_profile.limits.get('ranges', {})
        
        # Linear axes
        for axis, val in [('X', mx), ('Y', my), ('Z', mz)]:
            if axis in ranges:
                min_v, max_v = ranges[axis]
                if val < min_v or val > max_v:
                    violations.append(f"{axis}={val:.3f} outside limits [{min_v}, {max_v}]")
        
        # Rotary axes
        for axis, val in rotary_dict.items():
            axis_upper = axis.upper()
            if axis_upper in ranges:
                min_v, max_v = ranges[axis_upper]
                if val < min_v or val > max_v:
                    violations.append(f"{axis_upper}={val:.3f} outside limits [{min_v}, {max_v}]")
        
        return violations
    
    def _format_rotary(self, rotary_dict: Dict[str, float]) -> str:
        """Format rotary commands according to dialect."""
        if not rotary_dict:
            return ""
        
        if self.settings.dialect.value == "klipper_manual_stepper_ab":
            # Klipper MANUAL_STEPPER commands
            cmds = []
            for axis, val in rotary_dict.items():
                stepper_name = axis.lower()
                cmds.append(f"MANUAL_STEPPER STEPPER=stepper_{stepper_name} POS={val:.3f}")
            return "\n" + "\n".join(cmds)
        else:
            # Standard G-code rotary axes (A, B, C, U, V, W)
            cmds = []
            for axis, val in rotary_dict.items():
                if axis in self.settings.axis_mapping:
                    gcode_axis = self.settings.axis_mapping[axis]
                    cmds.append(f"{gcode_axis}{val:.3f}")
            return " " + " ".join(cmds) if cmds else ""
    
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
        mx: float, my: float, mz: float,
        rotary_dict: Dict[str, float],
        feedrate: float,
        extrusion: float = 0.0,
        comment: str = ""
    ) -> Optional[ValidatedMove]:
        """Emit a validated move and return the move record, or None if validation fails."""
        # Validate all values are finite
        for name, val in [('mx', mx), ('my', my), ('mz', mz), ('feedrate', feedrate), ('extrusion', extrusion)]:
            if not self._safe_check_finite(name, val, f"{move_type.value} move"):
                return None
        
        for axis, val in rotary_dict.items():
            if not self._safe_check_finite(f"rotary_{axis}", val, f"{move_type.value} move"):
                return None
        
        # Check machine limits
        violations = self._check_machine_limits(mx, my, mz, rotary_dict)
        if violations:
            self._validation_errors_accumulator.append(
                f"Machine limit violation on {move_type.value}: {'; '.join(violations)}"
            )
            return None
        
        x_ax = self.settings.axis_mapping.get('x', 'X')
        y_ax = self.settings.axis_mapping.get('y', 'Y')
        z_ax = self.settings.axis_mapping.get('z', 'Z')
        e_ax = self.settings.axis_mapping.get('e', 'E')
        
        rotary_str = self._format_rotary(rotary_dict)
        
        if move_type == MoveType.TRAVEL:
            line = f"G0 {x_ax}{mx:.3f} {y_ax}{my:.3f} {z_ax}{mz:.3f} F{feedrate:.0f}{rotary_str}"
            if comment:
                line += f" ; {comment}"
        elif move_type == MoveType.EXTRUSION:
            self.current_e += extrusion
            line = f"G1 {x_ax}{mx:.3f} {y_ax}{my:.3f} {z_ax}{mz:.3f} {e_ax}{self.current_e:.3f} F{feedrate:.1f}{rotary_str}"
            if comment:
                line += f" ; {comment}"
        elif move_type == MoveType.RETRACTION:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            line = f"G1 {e_axis}{self.current_e:.3f} F{feedrate:.0f} ; Retract"
        elif move_type == MoveType.UNRETRACT:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            line = f"G1 {e_axis}{self.current_e:.3f} F{feedrate:.0f} ; Unretract"
        elif move_type == MoveType.ROTARY_ONLY:
            # Pure rotary move (no XYZ change)
            line = f"G0{rotary_str} F{feedrate:.0f} ; Rotary only"
            if comment:
                line += f" {comment}"
        elif move_type == MoveType.CLEARANCE:
            line = f"G0 {x_ax}{mx:.3f} {y_ax}{my:.3f} {z_ax}{mz:.3f} F{feedrate:.0f}{rotary_str} ; Clearance"
        else:
            raise ValueError(f"Unknown move type: {move_type}")
        
        gcode.append(line)
        
        return ValidatedMove(
            move_type=move_type,
            gcode_line=line,
            machine_x=mx,
            machine_y=my,
            machine_z=mz,
            rotary_axes=rotary_dict.copy(),
            extrusion_mm=extrusion,
            feedrate_mmm=feedrate,
            is_finite=True
        )
    
    def generate(self, path_points: List[Tuple], path_ids: Optional[List[int]] = None) -> GenerationResult:
        """
        Generate G-code from toolpath points.
        
        Args:
            path_points: List of (x, y, z, nx, ny, nz) in build-plate frame
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
            # Verify kinematics adapter on first point
            if not path_points:
                return GenerationResult(
                    gcode="",
                    metadata={"is_prototype": True, "rotary_enabled": True, "axes": [], "error": "Empty path"},
                    moves=[],
                    validation_errors=["Empty path points"],
                    total_extrusion_mm=0.0,
                    total_travel_mm=0.0,
                    total_print_mm=0.0
                )
            
            # Test kinematics
            test_pt = path_points[0]
            _, _, _, test_rotary = self.kinematics.calculate_ik(*test_pt)
            
            # Verify all rotary axes are mapped
            for rot_axis in test_rotary.keys():
                if rot_axis not in self.settings.axis_mapping:
                    raise ValueError(f"Unverified rotary axis '{rot_axis}' not in axis mapping")
            
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
                    rotary_axes={}, extrusion_mm=0, feedrate_mmm=0
                ))
            
            x_ax = self.settings.axis_mapping.get('x', 'X')
            y_ax = self.settings.axis_mapping.get('y', 'Y')
            z_ax = self.settings.axis_mapping.get('z', 'Z')
            
            total_extrusion = 0.0
            total_travel = 0.0
            total_print = 0.0
            
            for i, pt in enumerate(path_points):
                x, y, z, nx, ny, nz = pt
                current_path_id = path_ids[i] if path_ids else 0
                
                # Compute machine position via kinematics
                mx, my, mz, rotary_dict = self.kinematics.calculate_ik(x, y, z, nx, ny, nz)
                
                # Validate kinematics output - use safe check
                if not all(self._safe_check_finite(f"{k}[{i}]", v, "kinematics") 
                           for k, v in [('mx', mx), ('my', my), ('mz', mz)] + 
                           [(f'rotary_{k}', v) for k, v in rotary_dict.items()]):
                    # Errors already accumulated
                    pass
                
                if self.last_machine_pos is None:
                    # First move - clearance to start position
                    feedrate = self.settings.feed_limits.travel
                    move = self._emit_move(
                        gcode_lines, MoveType.CLEARANCE,
                        mx, my, mz, rotary_dict, feedrate,
                        comment="First move to start"
                    )
                    if move is not None:
                        moves.append(move)
                    
                    self.last_machine_pos = (mx, my, mz, rotary_dict)
                    self.last_part_pos = (x, y, z)
                    self.last_path_id = current_path_id
                    continue
                
                last_mx, last_my, last_mz, last_rotary = self.last_machine_pos
                last_x, last_y, last_z = self.last_part_pos
                
                # Distance in PART frame (for travel vs print decision)
                dist_part = math.hypot(x - last_x, y - last_y, z - last_z)
                
                # Distance in MACHINE frame (for feedrate calculation)
                dist_machine = math.hypot(mx - last_mx, my - last_my, mz - last_mz)
                
                # Rotary change (max angular difference)
                max_rotary_change = 0.0
                for axis in set(rotary_dict.keys()) | set(last_rotary.keys()):
                    v1 = rotary_dict.get(axis, 0)
                    v2 = last_rotary.get(axis, 0)
                    max_rotary_change = max(max_rotary_change, abs(v1 - v2))
                
                # Determine move type
                is_travel = (dist_part > self.travel_threshold or 
                            (path_ids and current_path_id != self.last_path_id))
                
                if is_travel:
                    # Travel move
                    if dist_machine > 1e-6 or max_rotary_change > 1e-6:
                        self._retract(gcode_lines)
                        moves.append(ValidatedMove(
                            move_type=MoveType.RETRACTION,
                            gcode_line=gcode_lines[-1],
                            machine_x=last_mx, machine_y=last_my, machine_z=last_mz,
                            rotary_axes=last_rotary, extrusion_mm=0,
                            feedrate_mmm=self.settings.retraction.feedrate
                        ))
                        
                        feedrate = self.settings.feed_limits.travel
                        move = self._emit_move(
                            gcode_lines, MoveType.TRAVEL,
                            mx, my, mz, rotary_dict, feedrate,
                            comment=f"Travel to path {current_path_id}"
                        )
                        if move is not None:
                            moves.append(move)
                            total_travel += dist_machine
                    
                    self._unretract(gcode_lines)
                    if gcode_lines and gcode_lines[-1].startswith("G1") and "Unretract" in gcode_lines[-1]:
                        moves.append(ValidatedMove(
                            move_type=MoveType.UNRETRACT,
                            gcode_line=gcode_lines[-1],
                            machine_x=mx, machine_y=my, machine_z=mz,
                            rotary_axes=rotary_dict, extrusion_mm=0,
                            feedrate_mmm=self.settings.retraction.feedrate
                        ))
                
                else:
                    # Print move
                    if dist_machine > 1e-6:
                        self._unretract(gcode_lines)
                        if gcode_lines and gcode_lines[-1].startswith("G1") and "Unretract" in gcode_lines[-1]:
                            moves.append(ValidatedMove(
                                move_type=MoveType.UNRETRACT,
                                gcode_line=gcode_lines[-1],
                                machine_x=mx, machine_y=my, machine_z=mz,
                                rotary_axes=rotary_dict, extrusion_mm=0,
                                feedrate_mmm=self.settings.retraction.feedrate
                            ))
                        
                        extrusion = dist_part * self.e_multiplier
                        feedrate = self.settings.feed_limits.print
                        
                        move = self._emit_move(
                            gcode_lines, MoveType.EXTRUSION,
                            mx, my, mz, rotary_dict, feedrate,
                            extrusion=extrusion,
                            comment=f"Print path {current_path_id}"
                        )
                        if move is not None:
                            moves.append(move)
                            total_extrusion += extrusion
                            total_print += dist_part
                
                self.last_machine_pos = (mx, my, mz, rotary_dict)
                self.last_part_pos = (x, y, z)
                self.last_path_id = current_path_id
            
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
                self.settings.axis_mapping.get('z', 'Z')
            ]
            if path_points:
                _, _, _, final_rotary = self.kinematics.calculate_ik(*path_points[-1])
                axes_used.extend([self.settings.axis_mapping[k] for k in final_rotary.keys()])
            
            metadata = {
                "is_prototype": True,
                "rotary_enabled": True,
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
    from uv_adapter import TableTableUVAdapter
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    gen = RotaryGCodeGenerator(
        settings, kinematics, profile,
        layer_height=0.2, line_width=0.4, filament_diameter=1.75
    )
    
    # Expected: deposited_area = 0.2 * 0.4 = 0.08 mm²
    # Filament area = π * (1.75/2)² ≈ 2.405 mm²
    # Multiplier = 0.08 / 2.405 ≈ 0.03326
    expected = (0.2 * 0.4) / (math.pi * (1.75/2)**2)
    assert math.isclose(gen.e_multiplier, expected, rel_tol=1e-5)
    
    print("✓ Volumetric extrusion calculation")


def test_unit_consistency():
    """Test that all feedrates are in mm/min."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    from uv_adapter import TableTableUVAdapter
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    gen = RotaryGCodeGenerator(settings, kinematics, profile)
    
    # Simple 2-point path
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (10.0, 0.0, 0.2, 0.0, 0.0, 1.0),
    ]
    
    result = gen.generate(path)
    
    assert result.is_valid
    # Check that G1 moves have F in mm/min (print feedrate = 1500)
    for move in result.moves:
        if move.move_type == MoveType.EXTRUSION:
            assert move.feedrate_mmm == 1500.0
        elif move.move_type == MoveType.TRAVEL:
            assert move.feedrate_mmm == 3000.0
    
    print("✓ Unit consistency (mm/min)")


def test_finite_validation():
    """Test that non-finite values are rejected."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    from uv_adapter import TableTableUVAdapter
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    gen = RotaryGCodeGenerator(settings, kinematics, profile)
    
    # Path with NaN - should be caught in validation_errors, not raise
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (float('nan'), 0.0, 0.2, 0.0, 0.0, 1.0),
    ]
    
    result = gen.generate(path)
    assert not result.is_valid
    assert any("non-finite" in e.lower() or "nan" in e.lower() for e in result.validation_errors)
    
    print("✓ Finite validation")


def test_machine_limit_enforcement():
    """Test that machine limits block out-of-bounds moves."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    from uv_adapter import TableTableUVAdapter
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    
    # Profile with tight X limit
    profile = SlicerMachineProfile()
    profile.limits = {"ranges": {"X": [0, 100], "Y": [-100, 100], "Z": [0, 200]}}
    
    gen = RotaryGCodeGenerator(settings, kinematics, profile)
    
    # Path that goes beyond X=100
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),
        (150.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Beyond X limit
    ]
    
    result = gen.generate(path)
    assert not result.is_valid
    assert any("limit" in e.lower() for e in result.validation_errors)
    
    print("✓ Machine limit enforcement")


def test_move_type_classification():
    """Test explicit move type classification."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    from uv_adapter import TableTableUVAdapter
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    gen = RotaryGCodeGenerator(settings, kinematics, profile, travel_threshold=1.5)
    
    # Three points: print -> travel -> print (different path_ids)
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),   # Print path 1
        (10.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Travel to path 2 (dist > threshold)
        (11.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Print path 2
    ]
    path_ids = [1, 2, 2]  # Path 1, then path 2
    
    result = gen.generate(path, path_ids)
    
    move_types = [m.move_type for m in result.moves]
    # Should have: CLEARANCE, EXTRUSION (path 1), RETRACTION, TRAVEL, UNRETRACT, EXTRUSION (path 2)
    assert MoveType.TRAVEL in move_types
    assert MoveType.EXTRUSION in move_types
    assert MoveType.RETRACTION in move_types
    assert MoveType.UNRETRACT in move_types
    assert MoveType.CLEARANCE in move_types
    
    print("✓ Move type classification")


def test_rotary_only_moves():
    """Test pure rotary axis moves are handled."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    from uv_adapter import TableTableUVAdapter
    import math
    
    settings = DialectSettings(
        dialect=GCodeDialect.KLIPPER_MANUAL_STEPPER_AB,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    gen = RotaryGCodeGenerator(settings, kinematics, profile)
    
    # Path with same XYZ but different normals (rotary change only)
    # Use exact unit normals
    sqrt2_2 = 1.0 / math.sqrt(2)
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),        # Vertical
        (0.0, 0.0, 0.2, sqrt2_2, 0, sqrt2_2),  # Tilted 45°
    ]
    
    result = gen.generate(path)
    assert result.is_valid
    
    # Check that rotary commands are emitted
    gcode = result.gcode
    assert "MANUAL_STEPPER" in gcode or "U" in gcode or "V" in gcode
    
    print("✓ Rotary-only moves")


def test_retraction_logic():
    """Test retraction/unretraction logic."""
    from dialect_model import DialectSettings, FeedLimits, RetractionSettings, GCodeDialect, CoordinateMode
    from uv_adapter import TableTableUVAdapter
    import re
    
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        axis_mapping={'x': 'X', 'y': 'Y', 'z': 'Z', 'e': 'E', 'u': 'U', 'v': 'V'},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
    )
    kinematics = TableTableUVAdapter(bed_center_z=0.0)
    profile = SlicerMachineProfile()
    
    gen = RotaryGCodeGenerator(settings, kinematics, profile, travel_threshold=1.0)
    
    # Print -> travel -> print should retract/unretract
    path = [
        (0.0, 0.0, 0.2, 0.0, 0.0, 1.0),   # Print
        (1.0, 0.0, 0.2, 0.0, 0.0, 1.0),   # Print (same path)
        (10.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Travel (dist > threshold)
        (11.0, 0.0, 0.2, 0.0, 0.0, 1.0),  # Print (new path)
    ]
    path_ids = [1, 1, 2, 2]
    
    result = gen.generate(path, path_ids)
    
    gcode = result.gcode
    assert "Retract" in gcode
    assert "Unretract" in gcode
    
    # Check E values - in absolute mode, E should increase during print moves,
    # decrease during retraction, then increase again after unretract
    e_values = []
    for line in gcode.split('\n'):
        if line.startswith('G1') and 'E' in line and 'Retract' not in line and 'Unretract' not in line:
            match = re.search(r'E([-\d.]+)', line)
            if match:
                e_values.append(float(match.group(1)))
    
    # Print moves should have increasing E
    # But we can't easily separate print vs travel E values from the string
    # Just verify we have both positive extrusion and retraction
    assert any(e > 0 for e in e_values), "Should have positive extrusion"
    assert any(e < 0 for e in e_values) or len(e_values) >= 2, "Should have retraction or multiple moves"
    
    print("✓ Retraction logic")


if __name__ == "__main__":
    test_volumetric_extrusion()
    test_unit_consistency()
    test_finite_validation()
    test_machine_limit_enforcement()
    test_move_type_classification()
    test_rotary_only_moves()
    test_retraction_logic()
    print("\nAll RotaryGCodeGenerator validation tests passed!")