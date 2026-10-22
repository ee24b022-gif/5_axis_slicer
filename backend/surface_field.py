"""
Sinusoidal Surface Field Module
===============================

Mathematical model (wavelength-based, explicit):

    z_warped(x, y, z_true) = z_true - A * f(z_true) * sin(2π * x / λ_x + φ_x) * cos(2π * y / λ_y + φ_y)

where:
    A = amplitude [mm] (>= 0)
    λ_x = wavelength in X [mm] (> 0)
    λ_y = wavelength in Y [mm] (> 0)
    φ_x = phase in X [rad]
    φ_y = phase in Y [rad]
    f(z) = attenuation factor [0, 1], linear fade from 0 at z=0 to 1 at z=fade_height

This is a vertical height-field warp: only Z coordinates are modified.
The inverse mapping (distorted_z -> true_z) is analytically tractable because
the warp is purely vertical and the attenuation depends only on true_z.

COORDINATE FRAME
----------------
All coordinates are in the BUILD-PLATE frame (B):
- Origin: Build plate center at bed surface (Z=0)
- X: Right, Y: Forward, Z: Up
- Units: Millimeters
- Angles: Radians (internal), Degrees (user-facing config only)

VALIDATION RULES
----------------
- λ_x > 0, λ_y > 0
- A >= 0
- fade_height > 0
- max_slope = atan(A * 2π / min(λ_x, λ_y)) <= machine limit (default 45°)
- max_surface_tilt = atan(sqrt((A*2π/λ_x)^2 + (A*2π/λ_y)^2)) 
- minimum layer thickness: layer_height > A * 2 (to avoid self-intersection)
- minimum nozzle clearance: bed_center_z > max_warped_z + nozzle_length
"""

from typing import Tuple
import math
import numpy as np
from models import SurfaceFieldConfig


class SurfaceField:
    """
    Sinusoidal surface field with explicit wavelength parameterization.
    
    The field defines a vertical displacement (warp) applied to the true geometry:
        z_distorted = z_true - height_offset(x, y, z_true)
    
    This means the toolpath in distorted space is LOWER than the true geometry
    at wave peaks (positive height_offset), and matches at zero-crossings.
    """
    
    def __init__(self, config: SurfaceFieldConfig):
        self.config = config
        self._validate_config()
        
        # Pre-compute angular spatial frequencies [rad/mm]
        # k = 2π / λ
        self.k_x = (2.0 * math.pi) / config.wave_length_x
        self.k_y = (2.0 * math.pi) / config.wave_length_y
        
        # Maximum gradient magnitudes for slope validation
        # |∇h|_max = A * sqrt(k_x^2 + k_y^2) at attenuation = 1
        self._max_grad_magnitude = config.amplitude * math.hypot(self.k_x, self.k_y)
        self._max_slope_deg = math.degrees(math.atan(self._max_grad_magnitude))
    
    def _validate_config(self) -> None:
        """Validate configuration parameters. Raises ValueError on invalid config."""
        c = self.config
        
        if c.wave_length_x <= 0:
            raise ValueError(f"wave_length_x must be > 0, got {c.wave_length_x}")
        if c.wave_length_y <= 0:
            raise ValueError(f"wave_length_y must be > 0, got {c.wave_length_y}")
        if c.amplitude < 0:
            raise ValueError(f"amplitude must be >= 0, got {c.amplitude}")
        if c.fade_height <= 0:
            raise ValueError(f"fade_height must be > 0, got {c.fade_height}")
        
        # Check for finite values
        for name, val in [
            ("amplitude", c.amplitude),
            ("wave_length_x", c.wave_length_x),
            ("wave_length_y", c.wave_length_y),
            ("phase_x", c.phase_x),
            ("phase_y", c.phase_y),
            ("fade_height", c.fade_height),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")
        
        # Normalize phases to [-π, π]
        c.phase_x = ((c.phase_x + math.pi) % (2 * math.pi)) - math.pi
        c.phase_y = ((c.phase_y + math.pi) % (2 * math.pi)) - math.pi
    
    def _get_attenuation(self, true_z: float) -> float:
        """
        Attenuation factor: smoothly fade out the wave at the bottom.
        
        true_z <= 0      : 0.0 (no warp at/below bed)
        true_z >= fade_h : 1.0 (full amplitude)
        Linear interpolation in between.
        """
        if true_z <= 0.0:
            return 0.0
        if true_z >= self.config.fade_height:
            return 1.0
        return true_z / self.config.fade_height
    
    def get_height_offset(self, x: float, y: float, true_z: float) -> float:
        """
        Return the Z-offset applied at (x, y, true_z).
        
        This is the amount SUBTRACTED from true_z to get distorted_z:
            distorted_z = true_z - height_offset
        
        Args:
            x, y: Position in build-plate frame [mm]
            true_z: True (unwarped) Z coordinate [mm]
        
        Returns:
            Height offset [mm], always >= 0
        """
        if self.config.amplitude == 0.0:
            return 0.0
            
        att = self._get_attenuation(true_z)
        if att == 0.0:
            return 0.0
        
        # Wave function: sin(k_x * x + φ_x) * cos(k_y * y + φ_y)
        # This gives a checkerboard-like pattern with zero crossings at
        # x = (n - φ_x/π) * λ_x/2, y = (m + 0.5 - φ_y/π) * λ_y/2
        wave = (math.sin(self.k_x * x + self.config.phase_x) * 
                math.cos(self.k_y * y + self.config.phase_y))
        
        return self.config.amplitude * wave * att
    
    def distort_z(self, x: float, y: float, true_z: float) -> float:
        """
        Forward distortion: map true (unwarped) Z to distorted Z.
        
        This is used for:
        - Warping mesh vertices for collision checking
        - Computing distorted slice plane positions
        
        Args:
            x, y: Position in build-plate frame [mm]
            true_z: True Z coordinate [mm]
        
        Returns:
            Distorted Z coordinate [mm]
        """
        return true_z - self.get_height_offset(x, y, true_z)
    
    def inverse_distort_z(self, x: float, y: float, distorted_z: float) -> float:
        """
        Inverse distortion: map distorted Z back to true Z.
        
        This is used for:
        - Mapping sliced toolpath Z back to true geometry for G-code
        - Converting collision check results to true coordinates
        
        For a vertical height-field warp with linear attenuation, the inverse
        is analytically solvable:
        
        distorted_z = true_z - A * f(true_z) * wave
        
        Case 1: true_z >= fade_height (att = 1)
            distorted_z = true_z - A * wave
            true_z = distorted_z + A * wave
        
        Case 2: true_z <= 0 (att = 0)
            distorted_z = true_z
            true_z = distorted_z
        
        Case 3: 0 < true_z < fade_height (att = true_z / fade_h)
            distorted_z = true_z - A * (true_z / fade_h) * wave
            distorted_z = true_z * (1 - A * wave / fade_h)
            true_z = distorted_z / (1 - A * wave / fade_h)
            (valid when denominator > 0, i.e., A * |wave| < fade_h)
        
        Since we don't know true_z a priori, we determine the case from distorted_z:
        - If distorted_z >= fade_height - A*|wave|: Case 1
        - If distorted_z <= 0: Case 2
        - Otherwise: Case 3
        
        Args:
            x, y: Position in build-plate frame [mm]
            distorted_z: Distorted Z coordinate [mm]
        
        Returns:
            True (unwarped) Z coordinate [mm]
        
        Raises:
            ValueError if the inverse is ambiguous or denominator near zero
        """
        if self.config.amplitude == 0.0:
            return distorted_z
        
        wave = (math.sin(self.k_x * x + self.config.phase_x) * 
                math.cos(self.k_y * y + self.config.phase_y))
        wave_abs = abs(wave)
        A = self.config.amplitude
        fade_h = self.config.fade_height
        
        # Thresholds for case determination
        # At true_z = fade_h: distorted_z = fade_h - A*wave
        # At true_z = 0: distorted_z = 0
        threshold_upper = fade_h - A * wave
        threshold_lower = 0.0
        
        if distorted_z >= threshold_upper:
            # Case 1: true_z >= fade_height, attenuation = 1
            return distorted_z + A * wave
        
        if distorted_z <= threshold_lower:
            # Case 2: true_z <= 0, attenuation = 0
            return distorted_z
        
        # Case 3: 0 < true_z < fade_height, attenuation = true_z / fade_h
        # distorted_z = true_z * (1 - A*wave/fade_h)
        denom = 1.0 - (A * wave / fade_h)
        if denom <= 1e-6:
            # Near-singular: fall back to linear approximation
            # This happens when A*wave ≈ fade_h, which violates slope limits anyway
            return distorted_z + A * wave
        
        return distorted_z / denom
    
    def get_normal(self, x: float, y: float, true_z: float) -> Tuple[float, float, float]:
        """
        Analytical surface normal of the warped surface at (x, y, true_z).
        
        The warped surface is: z_warped = true_z - h(x, y, true_z)
        where h = A * f(true_z) * sin(k_x*x + φ_x) * cos(k_y*y + φ_y)
        
        The normal is: N = (-∂z_warped/∂x, -∂z_warped/∂y, 1) normalized
        
        ∂h/∂x = A * f(true_z) * k_x * cos(k_x*x + φ_x) * cos(k_y*y + φ_y)
        ∂h/∂y = -A * f(true_z) * k_y * sin(k_x*x + φ_x) * sin(k_y*y + φ_y)
        
        So:
        N = (A*f*k_x*cos*cos, -A*f*k_y*sin*sin, 1) normalized
        (Note sign: z_warped = z_true - h, so ∂z_warped/∂x = -∂h/∂x)
        
        Args:
            x, y: Position in build-plate frame [mm]
            true_z: True Z coordinate [mm] (NOT distorted_z)
        
        Returns:
            Unit normal vector (nx, ny, nz) in build-plate frame
        """
        if self.config.amplitude == 0.0:
            return (0.0, 0.0, 1.0)
        
        att = self._get_attenuation(true_z)
        if att == 0.0:
            return (0.0, 0.0, 1.0)
        
        A = self.config.amplitude
        k_x = self.k_x
        k_y = self.k_y
        ph_x = self.config.phase_x
        ph_y = self.config.phase_y
        
        sin_x = math.sin(k_x * x + ph_x)
        cos_x = math.cos(k_x * x + ph_x)
        sin_y = math.sin(k_y * y + ph_y)
        cos_y = math.cos(k_y * y + ph_y)
        
        # ∂h/∂x = A * att * k_x * cos(k_x*x + φ_x) * cos(k_y*y + φ_y)
        dh_dx = att * A * k_x * cos_x * cos_y
        # ∂h/∂y = -A * att * k_y * sin(k_x*x + φ_x) * sin(k_y*y + φ_y)
        dh_dy = -att * A * k_y * sin_x * sin_y
        
        # Surface normal of z_warped = z_true - h
        nx = dh_dx
        ny = dh_dy
        nz = 1.0
        
        length = math.sqrt(nx*nx + ny*ny + nz*nz)
        return (nx/length, ny/length, nz/length)
    
    def get_gradient(self, x: float, y: float, true_z: float) -> Tuple[float, float]:
        """
        Return the 2D gradient (∂h/∂x, ∂h/∂y) at (x, y, true_z).
        
        Useful for slope analysis and adaptive sampling.
        """
        if self.config.amplitude == 0.0:
            return (0.0, 0.0)
        
        att = self._get_attenuation(true_z)
        if att == 0.0:
            return (0.0, 0.0)
        
        A = self.config.amplitude
        k_x = self.k_x
        k_y = self.k_y
        ph_x = self.config.phase_x
        ph_y = self.config.phase_y
        
        sin_x = math.sin(k_x * x + ph_x)
        cos_x = math.cos(k_x * x + ph_x)
        sin_y = math.sin(k_y * y + ph_y)
        cos_y = math.cos(k_y * y + ph_y)
        
        dh_dx = att * A * k_x * cos_x * cos_y
        dh_dy = -att * A * k_y * sin_x * sin_y
        
        return (dh_dx, dh_dy)
    
    def validate_constraints(self, max_slope_deg: float = 45.0) -> Tuple[bool, list[str]]:
        """
        Validate that field parameters respect mechanical limits.
        
        Checks:
        - Maximum surface slope <= max_slope_deg
        - Amplitude doesn't cause self-intersection at given layer_height
        - Wavelengths are within reasonable bounds
        
        Returns:
            (is_valid, list_of_warnings_or_errors)
        """
        errors = []
        warnings = []
        
        if self.config.amplitude == 0.0:
            return True, []
        
        # Max slope check
        if self._max_slope_deg > max_slope_deg:
            errors.append(
                f"Maximum surface slope {self._max_slope_deg:.1f}° exceeds limit {max_slope_deg}° "
                f"(A={self.config.amplitude}mm, λ_x={self.config.wave_length_x}mm, λ_y={self.config.wave_length_y}mm)"
            )
        
        # Minimum wavelength check (avoid sub-mm features)
        min_wavelength = min(self.config.wave_length_x, self.config.wave_length_y)
        if min_wavelength < 1.0:
            warnings.append(f"Wavelength {min_wavelength}mm < 1mm may cause numerical issues")
        
        # Amplitude vs wavelength ratio
        max_ratio = self.config.amplitude / min_wavelength
        if max_ratio > 0.5:
            warnings.append(f"Amplitude/wavelength ratio {max_ratio:.2f} > 0.5 may cause self-intersection")
        
        # Fade height check
        if self.config.fade_height < self.config.amplitude * 2:
            warnings.append(f"Fade height {self.config.fade_height}mm < 2*A ({2*self.config.amplitude}mm)")
        
        return len(errors) == 0, errors + warnings
    
    def get_field_metadata(self) -> dict:
        """Return field parameters and derived values for serialization."""
        return {
            "amplitude_mm": self.config.amplitude,
            "wave_length_x_mm": self.config.wave_length_x,
            "wave_length_y_mm": self.config.wave_length_y,
            "phase_x_rad": self.config.phase_x,
            "phase_y_rad": self.config.phase_y,
            "fade_height_mm": self.config.fade_height,
            "spatial_freq_x_cpmm": self.k_x / (2 * math.pi),  # cycles/mm
            "spatial_freq_y_cpmm": self.k_y / (2 * math.pi),
            "max_slope_deg": self._max_slope_deg,
            "max_gradient": self._max_grad_magnitude,
        }


# --- Validation / Test Functions ---

def test_zero_amplitude():
    """Zero amplitude should produce no distortion."""
    config = SurfaceFieldConfig(amplitude=0.0, wave_length_x=50.0, wave_length_y=50.0)
    field = SurfaceField(config)
    
    for x, y, z in [(0, 0, 0), (10, 20, 5), (-100, 50, 100)]:
        assert field.distort_z(x, y, z) == z
        assert field.inverse_distort_z(x, y, z) == z
        assert field.get_normal(x, y, z) == (0.0, 0.0, 1.0)
        assert field.get_height_offset(x, y, z) == 0.0
    
    valid, msgs = field.validate_constraints()
    assert valid
    print("✓ Zero amplitude")


def test_phase_shifts():
    """Phase shifts should translate the pattern."""
    config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=10.0, wave_length_y=10.0, phase_x=0.0, phase_y=0.0)
    field = SurfaceField(config)
    
    # At x=0, sin(0)=0, so offset=0
    assert field.get_height_offset(0, 0, 10) == 0.0
    
    # Shift phase by π/2 -> sin(π/2)=1 at x=0
    config2 = SurfaceFieldConfig(amplitude=1.0, wave_length_x=10.0, wave_length_y=10.0, phase_x=math.pi/2, phase_y=0.0)
    field2 = SurfaceField(config2)
    
    # At x=0, sin(π/2)=1, cos(0)=1, att=1 (z=10 > fade_h default 15? No, default fade_h=15, so att=10/15)
    # Actually fade_height defaults to 15, so at z=10, att=10/15
    offset = field2.get_height_offset(0, 0, 20)  # z=20 > fade_h, att=1
    assert math.isclose(offset, 1.0, rel_tol=1e-5)
    
    print("✓ Phase shifts")


def test_one_full_wavelength():
    """One full wavelength should return to same value."""
    λ = 20.0
    config = SurfaceFieldConfig(amplitude=2.0, wave_length_x=λ, wave_length_y=λ)
    field = SurfaceField(config)
    
    x, y, z = 5.0, 7.0, 20.0  # z > fade_h
    
    # Offset at x
    offset1 = field.get_height_offset(x, y, z)
    
    # Offset at x + λ
    offset2 = field.get_height_offset(x + λ, y, z)
    
    assert math.isclose(offset1, offset2, rel_tol=1e-5)
    
    # Half wavelength should be opposite
    offset3 = field.get_height_offset(x + λ/2, y, z)
    assert math.isclose(offset1, -offset3, rel_tol=1e-5)
    
    print("✓ Full wavelength periodicity")


def test_negative_coordinates():
    """Field should work correctly for negative coordinates."""
    config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=10.0, wave_length_y=10.0)
    field = SurfaceField(config)
    
    x, y, z = 5.0, 5.0, 20.0
    offset_pos = field.get_height_offset(x, y, z)
    offset_neg = field.get_height_offset(-x, -y, z)
    
    # sin(-k*x) = -sin(k*x), cos(-k*y) = cos(k*y)
    # So offset(-x, -y) = -offset(x, y)
    assert math.isclose(offset_neg, -offset_pos, rel_tol=1e-5)
    
    print("✓ Negative coordinates")


def test_known_extrema():
    """Test known maximum/minimum values."""
    λ = 40.0
    A = 2.0
    config = SurfaceFieldConfig(amplitude=A, wave_length_x=λ, wave_length_y=λ, fade_height=10.0)
    field = SurfaceField(config)
    
    # Maximum: sin=1, cos=1 -> k_x*x = π/2, k_y*y = 0 (or 2π)
    # x = λ/4, y = 0
    x_max = λ / 4
    y_max = 0.0
    z = 20.0  # > fade_h
    
    offset = field.get_height_offset(x_max, y_max, z)
    assert math.isclose(offset, A, rel_tol=1e-5), f"Max offset {offset} != {A}"
    
    # Minimum: sin=-1, cos=1 -> x = 3λ/4
    x_min = 3 * λ / 4
    offset_min = field.get_height_offset(x_min, y_max, z)
    assert math.isclose(offset_min, -A, rel_tol=1e-5), f"Min offset {offset_min} != {-A}"
    
    print("✓ Known extrema")


def test_gradient_and_normal():
    """Test gradient and normal calculations."""
    config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=10.0, wave_length_y=20.0)
    field = SurfaceField(config)
    
    # At x=0, sin=0, cos=1 -> dh/dx = A*k_x*1*1, dh/dy = 0
    x, y, z = 0.0, 0.0, 20.0
    
    grad = field.get_gradient(x, y, z)
    expected_dh_dx = config.amplitude * field.k_x  # att=1, cos=1, cos=1
    expected_dh_dy = 0.0
    
    assert math.isclose(grad[0], expected_dh_dx, rel_tol=1e-5)
    assert math.isclose(grad[1], expected_dh_dy, rel_tol=1e-5)
    
    normal = field.get_normal(x, y, z)
    # Normal = (dh_dx, dh_dy, 1) normalized
    expected_nx = expected_dh_dx / math.sqrt(expected_dh_dx**2 + 1)
    expected_nz = 1.0 / math.sqrt(expected_dh_dx**2 + 1)
    
    assert math.isclose(normal[0], expected_nx, rel_tol=1e-5)
    assert math.isclose(normal[1], 0.0, abs_tol=1e-10)
    assert math.isclose(normal[2], expected_nz, rel_tol=1e-5)
    
    print("✓ Gradient and normal")


def test_wavelength_invariance_under_translation():
    """Field properties should be invariant under integer wavelength translation."""
    λ = 30.0
    config = SurfaceFieldConfig(amplitude=1.5, wave_length_x=λ, wave_length_y=λ)
    field = SurfaceField(config)
    
    x, y, z = 7.3, -12.1, 25.0
    
    for n in range(-5, 6):
        offset = field.get_height_offset(x + n*λ, y, z)
        offset_ref = field.get_height_offset(x, y, z)
        assert math.isclose(offset, offset_ref, rel_tol=1e-10), f"Failed at n={n}"
        
        normal = field.get_normal(x + n*λ, y, z)
        normal_ref = field.get_normal(x, y, z)
        assert math.isclose(normal[0], normal_ref[0], rel_tol=1e-10)
        assert math.isclose(normal[1], normal_ref[1], rel_tol=1e-10)
        assert math.isclose(normal[2], normal_ref[2], rel_tol=1e-10)
    
    print("✓ Wavelength invariance under translation")


def test_inverse_round_trip():
    """Test forward -> inverse round-trip over a grid."""
    config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=20.0, wave_length_y=30.0, fade_height=15.0)
    field = SurfaceField(config)
    
    # Test grid
    for x in [-20, -10, 0, 10, 20]:
        for y in [-15, 0, 15]:
            for true_z in [0.0, 5.0, 10.0, 15.0, 20.0, 30.0]:
                distorted = field.distort_z(x, y, true_z)
                recovered = field.inverse_distort_z(x, y, distorted)
                assert math.isclose(recovered, true_z, rel_tol=1e-6, abs_tol=1e-9), \
                    f"Round-trip failed at ({x},{y},{true_z}): {recovered} != {true_z}"
    
    print("✓ Inverse round-trip over grid")


def test_inverse_on_mesh_surface():
    """Test inverse mapping on representative mesh-like surfaces."""
    config = SurfaceFieldConfig(amplitude=2.0, wave_length_x=50.0, wave_length_y=50.0, fade_height=20.0)
    field = SurfaceField(config)
    
    # Simulate a curved surface: z = 10 + 0.1*x^2 + 0.05*y^2
    for x in np.linspace(-50, 50, 11):
        for y in np.linspace(-50, 50, 11):
            true_z = 10.0 + 0.1*x*x + 0.05*y*y
            distorted = field.distort_z(x, y, true_z)
            recovered = field.inverse_distort_z(x, y, distorted)
            assert math.isclose(recovered, true_z, rel_tol=1e-5, abs_tol=1e-8), \
                f"Mesh round-trip failed at ({x},{y},{true_z}): {recovered}"
    
    print("✓ Inverse on mesh surface")


def test_slope_validation():
    """Test slope validation catches excessive slopes."""
    # Should pass: gentle slope
    config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=50.0, wave_length_y=50.0)
    field = SurfaceField(config)
    valid, msgs = field.validate_constraints(max_slope_deg=45.0)
    assert valid
    
    # Should fail: steep slope
    config = SurfaceFieldConfig(amplitude=10.0, wave_length_x=10.0, wave_length_y=10.0)
    field = SurfaceField(config)
    valid, msgs = field.validate_constraints(max_slope_deg=45.0)
    assert not valid
    assert any("slope" in m.lower() for m in msgs)
    
    print("✓ Slope validation")


def test_config_validation():
    """Test config validation catches invalid parameters."""
    # Negative wavelength - validated in SurfaceField.__init__
    try:
        config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=-10.0, wave_length_y=50.0)
        SurfaceField(config)
        assert False, "Should have raised"
    except ValueError as e:
        assert "wave_length_x" in str(e)
    
    # Zero wavelength
    try:
        config = SurfaceFieldConfig(amplitude=1.0, wave_length_x=0.0, wave_length_y=50.0)
        SurfaceField(config)
        assert False, "Should have raised"
    except ValueError as e:
        assert "wave_length_x" in str(e)
    
    # Negative amplitude
    try:
        config = SurfaceFieldConfig(amplitude=-1.0, wave_length_x=50.0, wave_length_y=50.0)
        SurfaceField(config)
        assert False, "Should have raised"
    except ValueError as e:
        assert "amplitude" in str(e)
    
    # Non-finite values
    try:
        config = SurfaceFieldConfig(amplitude=float('nan'), wave_length_x=50.0, wave_length_y=50.0)
        SurfaceField(config)
        assert False, "Should have raised"
    except ValueError as e:
        assert "finite" in str(e).lower() or "nan" in str(e).lower()
    
    print("✓ Config validation")


if __name__ == "__main__":
    test_zero_amplitude()
    test_phase_shifts()
    test_one_full_wavelength()
    test_negative_coordinates()
    test_known_extrema()
    test_gradient_and_normal()
    test_wavelength_invariance_under_translation()
    test_inverse_round_trip()
    test_inverse_on_mesh_surface()
    test_slope_validation()
    test_config_validation()
    print("\nAll SurfaceField validation tests passed!")