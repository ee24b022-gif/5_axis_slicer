from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import numpy as np

# 1. Machine & Job Configurations
@dataclass
class MachineProfile:
    """Defines the physical limits and configuration of the 5-axis machine."""
    max_feedrate_xy: float = 3000.0   # mm/min
    max_feedrate_z: float = 300.0     # mm/min
    max_feedrate_uv: float = 1800.0   # deg/min (rotary axes)
    max_accel_xy: float = 500.0       # mm/s^2
    nozzle_diameter: float = 0.4      # mm
    filament_diameter: float = 1.75   # mm
    # Envelope for collision (cylinder approximation)
    nozzle_length: float = 40.0
    nozzle_holder_radius: float = 5.0

@dataclass
class SurfaceFieldConfig:
    """Defines the sinusoidal surface field parameters."""
    amplitude: float = 0.0
    wave_length_x: float = 50.0  # inverse of frequency
    wave_length_y: float = 50.0
    phase_x: float = 0.0
    phase_y: float = 0.0
    fade_height: float = 15.0

# 2. Geometry & Mesh Models
@dataclass
class CanonicalMesh:
    """Standardized representation of the input mesh."""
    vertices: np.ndarray  # Shape: (N, 3)
    faces: np.ndarray     # Shape: (M, 3)
    normals: np.ndarray   # Shape: (M, 3)
    bounds_min: Tuple[float, float, float]
    bounds_max: Tuple[float, float, float]

@dataclass
class SurfaceSample:
    """A specific point evaluated on the Surface Field."""
    position: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    gradient_magnitude: float
    curvature: float
    is_valid: bool = True

@dataclass
class SliceFrame:
    """Local coordinate frame for a field-aware layer."""
    layer_idx: int
    z_base: float
    effective_thickness: float
    field_normal: Tuple[float, float, float]

# 3. Path & Kinematics Models
@dataclass
class FeaturePath:
    """Authoritative representation of a toolpath feature."""
    points: List[Tuple[float, float, float]]
    normals: List[Tuple[float, float, float]]
    layer_idx: int
    feature_type: str  # 'perimeter', 'infill', 'solid_infill', 'travel'
    path_id: int
    target_bead_width: float = 0.4
    effective_thickness: float = 0.2
    is_travel: bool = False

@dataclass
class MachinePose:
    """A mechanically valid pose for the machine."""
    x: float
    y: float
    z: float
    u: float  # Primary rotary (e.g., A or B axis)
    v: float  # Secondary rotary (e.g., C axis)
    feedrate_limit: float
    is_valid: bool = True

# 4. Collision & Diagnostics
@dataclass
class CollisionReport:
    """Report generated if a sweep test fails."""
    path_id: int
    layer_idx: int
    point_index: int
    clearance: float
    limiting_surface: str  # 'bed', 'part', 'machine_limit'
    suggested_remedy: str

@dataclass
class SliceJobResult:
    """The final result of the slicing job to be sent to the frontend."""
    job_id: str
    feature_paths: List[FeaturePath]
    gcode: str
    diagnostics: List[str]
    collision_reports: List[CollisionReport]
    stage_timings: Dict[str, float] = field(default_factory=dict)
