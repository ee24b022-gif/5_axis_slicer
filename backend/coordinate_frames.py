"""
Coordinate Frame Contract for 5-Axis Slicer Pipeline
=====================================================

This module defines the single source of truth for all coordinate frames,
transformations, and conventions used throughout the slicing pipeline.

FRAME DEFINITIONS
-----------------

1. MODEL/WORLD FRAME (M)
   - Origin: Arbitrary (STL file coordinates)
   - Axes: X right, Y forward, Z up
   - Handedness: Right-handed
   - Units: Millimeters
   - Notes: Input STL vertices live here. Centered/scaled by load_stl().

2. BUILD-PLATE FRAME (B) 
   - Origin: Center of build plate at bed surface (Z=0)
   - Axes: X right, Y forward, Z up
   - Handedness: Right-handed
   - Units: Millimeters
   - Notes: After load_stl() positioning (model_scale, rotation, pos_x, pos_y,
     and Z-floor shift so min_z = 0). This is the primary slicing frame.

3. TOOL/NOZZLE FRAME (T)
   - Origin: Nozzle tip
   - Axes: X right, Y forward, Z along nozzle axis (pointing from tip into heater block)
   - Handedness: Right-handed
   - Units: Millimeters (position), Radians (orientation)
   - Notes: Z axis aligned with surface normal at deposition point.

4. MACHINE-AXIS FRAME (A) - Linear axes only
   - Origin: Machine home (typically build plate center at Z=0)
   - Axes: X, Y, Z as linear actuators
   - Handedness: Right-handed
   - Units: Millimeters
   - Notes: Direct mapping from Build-Plate frame for 3-axis machines.
     For 5-axis, this is the linear actuator position after rotary transform.

5. ROTARY-AXIS FRAME (R) - AC_TABLE convention (Fractal 5 Pro / Klipper)
   - Axes: A (tilt about X), C (rotation about Z)
   - Convention: AC_TABLE = U-tilt-about-X, V-rotation-about-Z
   - Rotation order: R_total = R_u @ R_v (first V about Z, then U about X)
   - U (A-axis): Tilt about machine X, range [-120°, 120°]
   - V (C-axis): Rotation about machine Z, range [-360°, 360°]
   - Handedness: Right-handed rotations (positive = CCW when looking along +axis)
   - Units: Degrees (machine), Radians (internal math)
   - Notes: This matches the Klipper MANUAL_STEPPER convention used in
     fractal_5_pro_provisional profile. The UV adapter computes (u, v) in degrees.

6. BED / COLLISION-ENVELOPE FRAME (E)
   - Origin: Same as Build-Plate frame (B)
   - Axes: X, Y, Z same as Build-Plate
   - Handedness: Right-handed
   - Units: Millimeters
   - Notes: Used for collision checking. Bed plane at Z = -bed_center_z.
     Printed material exists at Z <= current_layer_z.

TRANSFORMATION CHAIN
--------------------

Model (M) 
  -> [load_stl: scale, rotate XYZ, translate XY, Z-floor] 
  -> Build-Plate (B)
  -> [SurfaceField.distort_z: apply sinusoidal warp] 
  -> Warped Build-Plate (B')
  -> [Slice at Z planes in B'] 
  -> 2D contours in (X, Y) at each Z'
  -> [AreaLogic: offset, infill] 
  -> Toolpath in (X, Y, Z') in B'
  -> [SurfaceField.inverse_distort_z + normal] 
  -> Toolpath in (X, Y, Z, Nx, Ny, Nz) in B (true geometry)
  -> [Auto-segment: rotate about horizontal axis if enabled] 
  -> Toolpath in Tilted Frame (if auto_segment)
  -> [TableTableUVAdapter.calculate_ik] 
  -> Machine-Axis (A) + Rotary (R) commands
  -> G-code

SIGN CONVENTIONS
----------------

- Rotations: Right-hand rule. Positive angle = CCW when looking from origin 
  toward positive axis direction.
- Euler order for load_stl(): Rz * Ry * Rx (rotate X, then Y, then Z)
- Surface field phase: sin(freq_x * x + phase_x) * cos(freq_y * y + phase_y)
- UV adapter: v = atan2(nx, ny) [rotation about Z], u = atan2(hypot(nx,ny), nz) [tilt about X]

UNITS
-----

- All positions: millimeters (mm)
- All angles in math: radians (rad)
- All angles in machine profile / G-code: degrees (deg)
- Feedrates: mm/min (linear), deg/min (rotary)
- Layer height: mm
- Wave amplitude: mm
- Wave length: mm
- Frequency: cycles/mm (1/mm) - DERIVED, not user-facing

VALIDATION RULES
----------------

- wave_length_x > 0, wave_length_y > 0
- amplitude >= 0
- max_slope = atan(amplitude * 2π / wavelength) <= machine limit (default 45°)
- All normals must be unit length (|n| = 1 ± 1e-5)
- No NaN or infinite values in any transform output
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional
from enum import Enum


class RotationOrder(Enum):
    """Explicit rotation order for Euler sequences."""
    XYZ = "XYZ"  # Rz @ Ry @ Rx
    ZYX = "ZYX"  # Rx @ Ry @ Rz
    AC_TABLE = "AC_TABLE"  # R_u @ R_v (tilt about X, then rotate about Z)


@dataclass(frozen=True)
class FrameTransform:
    """Immutable 4x4 homogeneous transform matrix with metadata."""
    matrix: np.ndarray  # shape (4, 4)
    from_frame: str
    to_frame: str
    
    def __post_init__(self):
        assert self.matrix.shape == (4, 4), "Transform must be 4x4"
        assert np.all(np.isfinite(self.matrix)), "Transform contains non-finite values"
    
    def apply_point(self, point: np.ndarray) -> np.ndarray:
        """Apply transform to a 3D point (homogeneous coords)."""
        p = np.array([point[0], point[1], point[2], 1.0], dtype=float)
        result = self.matrix @ p
        if abs(result[3]) > 1e-12:
            result = result / result[3]
        return result[:3]
    
    def apply_vector(self, vector: np.ndarray) -> np.ndarray:
        """Apply transform to a 3D vector (no translation)."""
        v = np.array([vector[0], vector[1], vector[2], 0.0], dtype=float)
        result = self.matrix @ v
        return result[:3]
    
    def inverse(self) -> 'FrameTransform':
        """Return inverse transform."""
        inv_matrix = np.linalg.inv(self.matrix)
        return FrameTransform(inv_matrix, self.to_frame, self.from_frame)
    
    def compose(self, other: 'FrameTransform') -> 'FrameTransform':
        """Compose this transform after other (self @ other)."""
        assert self.from_frame == other.to_frame, f"Frame mismatch: {other.to_frame} != {self.from_frame}"
        return FrameTransform(self.matrix @ other.matrix, other.from_frame, self.to_frame)


def translation_matrix(tx: float, ty: float, tz: float) -> np.ndarray:
    """Create 4x4 translation matrix."""
    m = np.eye(4, dtype=float)
    m[0, 3] = tx
    m[1, 3] = ty
    m[2, 3] = tz
    return m


def rotation_matrix_x(angle_rad: float) -> np.ndarray:
    """Create 4x4 rotation matrix about X axis (right-hand rule)."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = np.eye(4, dtype=float)
    m[1, 1] = c
    m[1, 2] = -s
    m[2, 1] = s
    m[2, 2] = c
    return m


def rotation_matrix_y(angle_rad: float) -> np.ndarray:
    """Create 4x4 rotation matrix about Y axis (right-hand rule)."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m


def rotation_matrix_z(angle_rad: float) -> np.ndarray:
    """Create 4x4 rotation matrix about Z axis (right-hand rule)."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    return m


def scale_matrix(sx: float, sy: float, sz: float) -> np.ndarray:
    """Create 4x4 scale matrix."""
    m = np.eye(4, dtype=float)
    m[0, 0] = sx
    m[1, 1] = sy
    m[2, 2] = sz
    return m


def load_stl_transform(
    model_scale: float = 1.0,
    rot_x_deg: float = 0.0,
    rot_y_deg: float = 0.0,
    rot_z_deg: float = 0.0,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    z_floor_shift: float = 0.0,
) -> FrameTransform:
    """
    Build the Model->BuildPlate transform used by load_stl().
    
    Order: center -> scale -> rotate (X, Y, Z) -> translate XY -> Z-floor shift
    Rotation order: Rz @ Ry @ Rx (applied as Rx, then Ry, then Rz)
    """
    rad_x = math.radians(rot_x_deg)
    rad_y = math.radians(rot_y_deg)
    rad_z = math.radians(rot_z_deg)
    
    # Compose: T_xy @ Rz @ Ry @ Rx @ S @ T_center
    # Note: We don't have the center here, it's applied in load_stl() per-mesh
    # This function returns the transform *after* centering
    
    m = np.eye(4, dtype=float)
    # Scale
    m = scale_matrix(model_scale, model_scale, model_scale) @ m
    # Rotate X
    m = rotation_matrix_x(rad_x) @ m
    # Rotate Y
    m = rotation_matrix_y(rad_y) @ m
    # Rotate Z
    m = rotation_matrix_z(rad_z) @ m
    # Translate XY
    m = translation_matrix(pos_x, pos_y, 0.0) @ m
    # Z-floor shift
    m = translation_matrix(0.0, 0.0, -z_floor_shift) @ m
    
    return FrameTransform(m, "Model", "BuildPlate")


def ac_table_forward_kinematics(u_deg: float, v_deg: float, bed_center_z: float = 0.0) -> np.ndarray:
    """
    Compute the 4x4 transform from BuildPlate to Machine-Axis frame
    for AC_TABLE convention (U-tilt-about-X, V-rotate-about-Z).
    
    Rotation order: R_total = R_u @ R_v (first V about Z, then U about X)
    This matches TableTableUVAdapter.calculate_ik() internal math.
    
    Args:
        u_deg: Tilt angle about X axis (A-axis), degrees
        v_deg: Rotation angle about Z axis (C-axis), degrees
        bed_center_z: Z offset of rotation center from bed surface
    
    Returns:
        4x4 transform matrix: BuildPlate -> MachineAxis
    """
    u_rad = math.radians(u_deg)
    v_rad = math.radians(v_deg)
    
    # Rotation about Z (V / C-axis)
    cos_v, sin_v = math.cos(v_rad), math.sin(v_rad)
    R_v = np.array([
        [cos_v, -sin_v, 0, 0],
        [sin_v,  cos_v, 0, 0],
        [0,      0,     1, 0],
        [0,      0,     0, 1]
    ], dtype=float)
    
    # Rotation about X (U / A-axis)
    cos_u, sin_u = math.cos(u_rad), math.sin(u_rad)
    R_u = np.array([
        [1, 0,      0,      0],
        [0, cos_u, -sin_u,  0],
        [0, sin_u,  cos_u,  0],
        [0, 0,      0,      1]
    ], dtype=float)
    
    # Translation to rotation center
    T_center = translation_matrix(0, 0, bed_center_z)
    T_center_inv = translation_matrix(0, 0, -bed_center_z)
    
    # Full transform: T_center @ R_u @ R_v @ T_center_inv
    # Point in BuildPlate -> translate to rotation center -> rotate -> translate back
    transform = T_center @ R_u @ R_v @ T_center_inv
    
    return transform


def ac_table_inverse_kinematics(nx: float, ny: float, nz: float) -> Tuple[float, float]:
    """
    Compute (u_deg, v_deg) from a surface normal in BuildPlate frame.
    
    This is the analytical inverse of the AC_TABLE forward kinematics for orientation.
    
    Args:
        nx, ny, nz: Surface normal in BuildPlate frame (must be unit length)
    
    Returns:
        (u_deg, v_deg) - tilt about X, rotation about Z in degrees
    
    Raises:
        ValueError if normal is not unit length
    """
    n_len = math.hypot(nx, ny, nz)
    if not math.isclose(n_len, 1.0, rel_tol=1e-5):
        raise ValueError(f"Normal must be unit length, got {n_len}")
    
    # v = atan2(nx, ny)  [rotation about Z to align Y with normal's XY projection]
    v_rad = math.atan2(nx, ny)
    
    # u = atan2(hypot(nx, ny), nz)  [tilt about X to align Z with normal]
    xy_mag = math.hypot(nx, ny)
    u_rad = math.atan2(xy_mag, nz)
    
    return math.degrees(u_rad), math.degrees(v_rad)


def ac_table_apply_transform(
    x: float, y: float, z: float,
    u_deg: float, v_deg: float,
    bed_center_z: float = 0.0
) -> Tuple[float, float, float]:
    """
    Apply AC_TABLE transform to a point in BuildPlate frame.
    
    Returns (machine_x, machine_y, machine_z) in MachineAxis frame.
    """
    transform = ac_table_forward_kinematics(u_deg, v_deg, bed_center_z)
    # transform is a 4x4 matrix
    point = np.array([x, y, z, 1.0], dtype=float)
    result = transform @ point
    if abs(result[3]) > 1e-12:
        result = result / result[3]
    return float(result[0]), float(result[1]), float(result[2])


def ac_table_apply_normal(
    nx: float, ny: float, nz: float,
    u_deg: float, v_deg: float
) -> Tuple[float, float, float]:
    """
    Apply AC_TABLE rotation (Part -> Machine) to a normal vector.
    
    Rotation order: R_total = R_u @ R_v (first V about Z, then U about X)
    This matches TableTableUVAdapter.calculate_ik() internal math.
    
    Returns rotated normal in MachineAxis frame.
    """
    u_rad = math.radians(u_deg)
    v_rad = math.radians(v_deg)
    
    cos_v, sin_v = math.cos(v_rad), math.sin(v_rad)
    R_v = np.array([
        [cos_v, -sin_v, 0],
        [sin_v,  cos_v, 0],
        [0,      0,     1]
    ], dtype=float)
    
    cos_u, sin_u = math.cos(u_rad), math.sin(u_rad)
    R_u = np.array([
        [1, 0,      0],
        [0, cos_u, -sin_u],
        [0, sin_u,  cos_u]
    ], dtype=float)
    
    R_total = R_u @ R_v
    normal = np.array([nx, ny, nz], dtype=float)
    rotated = R_total @ normal
    
    # Re-normalize for numerical stability
    length = np.linalg.norm(rotated)
    if length > 0:
        rotated = rotated / length
    
    return float(rotated[0]), float(rotated[1]), float(rotated[2])


def ac_table_apply_normal_inverse(
    nx: float, ny: float, nz: float,
    u_deg: float, v_deg: float
) -> Tuple[float, float, float]:
    """
    Apply inverse AC_TABLE rotation (Machine -> Part) to a normal vector.
    
    Rotation order: R_total_inv = R_v^T @ R_u^T = R_v(-v) @ R_u(-u)
    
    Returns rotated normal in Part/BuildPlate frame.
    """
    u_rad = math.radians(u_deg)
    v_rad = math.radians(v_deg)
    
    # Inverse: R_v(-v) @ R_u(-u)
    cos_v, sin_v = math.cos(-v_rad), math.sin(-v_rad)
    R_v_inv = np.array([
        [cos_v, -sin_v, 0],
        [sin_v,  cos_v, 0],
        [0,      0,     1]
    ], dtype=float)
    
    cos_u, sin_u = math.cos(-u_rad), math.sin(-u_rad)
    R_u_inv = np.array([
        [1, 0,      0],
        [0, cos_u, -sin_u],
        [0, sin_u,  cos_u]
    ], dtype=float)
    
    R_total_inv = R_v_inv @ R_u_inv
    normal = np.array([nx, ny, nz], dtype=float)
    rotated = R_total_inv @ normal
    
    # Re-normalize for numerical stability
    length = np.linalg.norm(rotated)
    if length > 0:
        rotated = rotated / length
    
    return float(rotated[0]), float(rotated[1]), float(rotated[2])


def validate_frame_consistency(
    build_plate_bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]],
    machine_limits: dict,
    bed_center_z: float
) -> Tuple[bool, list[str]]:
    """
    Validate that the build plate fits within machine limits after transforms.
    
    Args:
        build_plate_bounds: ((min_x, min_y, min_z), (max_x, max_y, max_z)) in BuildPlate frame
        machine_limits: Dict with 'ranges' mapping axis -> (min, max)
        bed_center_z: Z offset of rotation center
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    (min_x, min_y, min_z), (max_x, max_y, max_z) = build_plate_bounds
    
    # Check linear axis limits (assuming BuildPlate ≈ MachineAxis for linear)
    if 'X' in machine_limits.get('ranges', {}):
        lim_min, lim_max = machine_limits['ranges']['X']
        if min_x < lim_min or max_x > lim_max:
            errors.append(f"X bounds [{min_x}, {max_x}] exceed machine limits [{lim_min}, {lim_max}]")
    
    if 'Y' in machine_limits.get('ranges', {}):
        lim_min, lim_max = machine_limits['ranges']['Y']
        if min_y < lim_min or max_y > lim_max:
            errors.append(f"Y bounds [{min_y}, {max_y}] exceed machine limits [{lim_min}, {lim_max}]")
    
    if 'Z' in machine_limits.get('ranges', {}):
        lim_min, lim_max = machine_limits['ranges']['Z']
        # Account for bed_center_z offset
        if (min_z - bed_center_z) < lim_min or (max_z - bed_center_z) > lim_max:
            errors.append(f"Z bounds [{min_z - bed_center_z}, {max_z - bed_center_z}] exceed machine limits [{lim_min}, {lim_max}]")
    
    # Check rotary limits if present
    if 'A' in machine_limits.get('ranges', {}):
        lim_min, lim_max = machine_limits['ranges']['A']
        # We can't know the exact U range without the toolpath, but warn if limits seem wrong
        if lim_min >= lim_max:
            errors.append(f"A-axis limits invalid: min {lim_min} >= max {lim_max}")
    
    if 'B' in machine_limits.get('ranges', {}):
        lim_min, lim_max = machine_limits['ranges']['B']
        if lim_min >= lim_max:
            errors.append(f"B-axis limits invalid: min {lim_min} >= max {lim_max}")
    
    return len(errors) == 0, errors


# --- Round-trip test helpers ---

def test_identity_transforms():
    """Verify identity transforms work correctly."""
    # Translation identity
    t = translation_matrix(0, 0, 0)
    assert np.allclose(t, np.eye(4))
    
    # Rotation identity
    rx = rotation_matrix_x(0)
    ry = rotation_matrix_y(0)
    rz = rotation_matrix_z(0)
    assert np.allclose(rx, np.eye(4))
    assert np.allclose(ry, np.eye(4))
    assert np.allclose(rz, np.eye(4))
    
    # Scale identity
    s = scale_matrix(1, 1, 1)
    assert np.allclose(s, np.eye(4))


def test_pure_translations():
    """Verify pure translations work correctly."""
    t = translation_matrix(10, 20, 30)
    p = np.array([1, 2, 3], dtype=float)
    result = FrameTransform(t, "A", "B").apply_point(p)
    assert np.allclose(result, [11, 22, 33])


def test_rotary_round_trip():
    """Verify AC_TABLE forward/inverse kinematics round-trip.
    
    The UV adapter computes u,v such that R_total @ normal_part = (0,0,1)
    where R_total = R_u @ R_v transforms from Part to Machine frame.
    So the round-trip is: R_total @ normal_part ≈ (0,0,1).
    """
    # Test various normals
    test_normals = [
        (0, 0, 1),      # Vertical
        (1, 0, 0),      # +X
        (0, 1, 0),      # +Y
        (-1, 0, 0),     # -X
        (0, -1, 0),     # -Y
        (0.7071, 0, 0.7071),  # 45° tilt in XZ
        (0, 0.7071, 0.7071),  # 45° tilt in YZ
        (0.57735, 0.57735, 0.57735),  # Equal components
    ]
    
    for nx, ny, nz in test_normals:
        # Normalize
        length = math.hypot(nx, ny, nz)
        nx, ny, nz = nx/length, ny/length, nz/length
        
        u_deg, v_deg = ac_table_inverse_kinematics(nx, ny, nz)
        
        # Apply forward kinematics (Part -> Machine) to the normal
        # In machine frame, the nozzle is fixed along +Z, so the rotated normal should be (0,0,1)
        rot_nx, rot_ny, rot_nz = ac_table_apply_normal(nx, ny, nz, u_deg, v_deg)
        
        # The normal in Part frame, when transformed to Machine frame, should align with +Z
        assert math.isclose(rot_nx, 0.0, abs_tol=1e-5), f"rot_nx should be 0: {rot_nx}"
        assert math.isclose(rot_ny, 0.0, abs_tol=1e-5), f"rot_ny should be 0: {rot_ny}"
        assert math.isclose(rot_nz, 1.0, rel_tol=1e-5), f"rot_nz should be 1: {rot_nz}"
        
        # Inverse: R_total^T @ (0,0,1) should give back the original normal
        # R_total^T = R_v^T @ R_u^T = R_v(-v) @ R_u(-u)
        inv_nx, inv_ny, inv_nz = ac_table_apply_normal_inverse(0, 0, 1, u_deg, v_deg)
        assert math.isclose(inv_nx, nx, rel_tol=1e-5, abs_tol=1e-10), f"inv nx mismatch: {inv_nx} vs {nx}"
        assert math.isclose(inv_ny, ny, rel_tol=1e-5, abs_tol=1e-10), f"inv ny mismatch: {inv_ny} vs {ny}"
        assert math.isclose(inv_nz, nz, rel_tol=1e-5, abs_tol=1e-10), f"inv nz mismatch: {inv_nz} vs {nz}"


def test_bed_plane_alignment():
    """Verify bed plane (Z=0 in BuildPlate) maps correctly."""
    # Bed plane in BuildPlate is Z=0
    # After AC_TABLE with bed_center_z, the rotation center is at Z=bed_center_z
    # A point at (0, 0, 0) in BuildPlate should rotate about (0, 0, bed_center_z)
    
    u_deg, v_deg = 30.0, 45.0
    bed_center_z = 50.0
    
    # Point on bed at origin
    mx, my, mz = ac_table_apply_transform(0, 0, 0, u_deg, v_deg, bed_center_z)
    
    # Should be on a circle of radius bed_center_z around the rotation center
    # Distance from rotation center (0, 0, bed_center_z) should be bed_center_z
    dist_from_center = math.hypot(mx, my, mz - bed_center_z)
    assert math.isclose(dist_from_center, bed_center_z, rel_tol=1e-5)


def test_known_tool_position_fixtures():
    """Test known tool positions from validation fixtures."""
    # From test_collision_exact.py: box at z in [38.42, 100]
    # Tip at (50, 50, 1.4), vertical nozzle
    # This is in BuildPlate frame
    
    u_deg, v_deg = 0.0, 0.0
    bed_center_z = 0.0  # Default for these tests
    
    mx, my, mz = ac_table_apply_transform(50, 50, 1.4, u_deg, v_deg, bed_center_z)
    assert math.isclose(mx, 50) and math.isclose(my, 50) and math.isclose(mz, 1.4)
    
    # Rotated normal
    nx, ny, nz = ac_table_apply_normal(0, 0, 1, u_deg, v_deg)
    assert math.isclose(nx, 0) and math.isclose(ny, 0) and math.isclose(nz, 1)


if __name__ == "__main__":
    # Run validation tests
    test_identity_transforms()
    print("✓ Identity transforms")
    
    test_pure_translations()
    print("✓ Pure translations")
    
    test_rotary_round_trip()
    print("✓ Rotary round-trip (IK/FK)")
    
    test_bed_plane_alignment()
    print("✓ Bed plane alignment")
    
    test_known_tool_position_fixtures()
    print("✓ Known tool position fixtures")
    
    print("\nAll coordinate frame validation tests passed!")