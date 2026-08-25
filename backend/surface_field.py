from typing import Tuple
import math
import numpy as np
from models import SurfaceFieldConfig

class SurfaceField:
    def __init__(self, config: SurfaceFieldConfig):
        self.config = config
        
        # We need frequencies to compute gradients analytically
        self.freq_x = (2.0 * math.pi) / config.wave_length_x if config.wave_length_x > 0 else 0
        self.freq_y = (2.0 * math.pi) / config.wave_length_y if config.wave_length_y > 0 else 0

    def _get_attenuation(self, true_z: float) -> float:
        """
        Calculates attenuation factor to smoothly fade out the wave at the bottom.
        true_z <= 0 : 0.0
        true_z >= fade_height : 1.0
        """
        if true_z <= 0.0:
            return 0.0
        if true_z >= self.config.fade_height:
            return 1.0
        return true_z / self.config.fade_height

    def get_height_offset(self, x: float, y: float, true_z: float) -> float:
        """
        Returns the z-offset applied to a specific (x,y) at a given base height.
        """
        if self.config.amplitude == 0.0:
            return 0.0
            
        att = self._get_attenuation(true_z)
        if att == 0.0:
            return 0.0
            
        wave = self.config.amplitude * math.sin(self.freq_x * x + self.config.phase_x) * math.cos(self.freq_y * y + self.config.phase_y)
        return wave * att

    def distort_z(self, x: float, y: float, true_z: float) -> float:
        """
        Forward distortion for mesh vertices and toolpath Z coordinates.
        """
        return true_z - self.get_height_offset(x, y, true_z)

    def inverse_distort_z(self, x: float, y: float, distorted_z: float) -> float:
        """
        Inverse mapping from a distorted Z back to the true Z.
        (Useful if slicing happens in distorted space and needs to be mapped back)
        """
        if self.config.amplitude == 0.0:
            return distorted_z
            
        # Approximation for the inverse if fade_height is involved
        wave = self.config.amplitude * math.sin(self.freq_x * x + self.config.phase_x) * math.cos(self.freq_y * y + self.config.phase_y)
        z_fade = self.config.fade_height - wave
        
        if distorted_z >= z_fade:
            return distorted_z + wave
        
        denom = 1.0 - (wave / self.config.fade_height)
        if denom <= 0.01:
            return distorted_z + wave # Fallback
            
        return distorted_z / denom

    def get_normal(self, x: float, y: float, true_z: float) -> Tuple[float, float, float]:
        """
        Returns the analytical normal vector of the field at a given point.
        Points purely up (0,0,1) if amplitude is 0 or attenuation is 0.
        """
        if self.config.amplitude == 0.0:
            return (0.0, 0.0, 1.0)
            
        att = self._get_attenuation(true_z)
        if att == 0.0:
            return (0.0, 0.0, 1.0)
            
        df_dx = att * self.config.amplitude * self.freq_x * math.cos(self.freq_x * x + self.config.phase_x) * math.cos(self.freq_y * y + self.config.phase_y)
        df_dy = -att * self.config.amplitude * self.freq_y * math.sin(self.freq_x * x + self.config.phase_x) * math.sin(self.freq_y * y + self.config.phase_y)
        
        nx, ny, nz = -df_dx, -df_dy, 1.0
        length = math.sqrt(nx*nx + ny*ny + nz*nz)
        return (nx/length, ny/length, nz/length)

    def validate_constraints(self, max_slope_deg: float = 45.0) -> bool:
        """
        Validates if the field parameters will exceed mechanical limits.
        max_slope = arctan( A * 2pi/lambda )
        """
        if self.config.amplitude == 0.0:
            return True
            
        max_grad_x = self.config.amplitude * self.freq_x
        max_grad_y = self.config.amplitude * self.freq_y
        max_slope_x = math.degrees(math.atan(max_grad_x))
        max_slope_y = math.degrees(math.atan(max_grad_y))
        
        return max_slope_x <= max_slope_deg and max_slope_y <= max_slope_deg
