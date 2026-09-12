import numpy as np
import math

class TableTableUVAdapter:
    """
    Transforms part coordinates/normals into machine coordinates 
    using the U-tilt-about-X, V-rotation-about-Z (AC_TABLE) convention.
    """
    def __init__(self, bed_center_z: float = 0.0):
        self.bed_center_z = bed_center_z

    def calculate_ik(self, x: float, y: float, z: float, nx: float, ny: float, nz: float):
        """
        Calculates machine XYZ and U/V (in degrees) for a given point and normal.
        Fails if normal is not a strict unit vector.
        """
        # Validate unit normal
        n_length = math.hypot(nx, ny, nz)
        if not math.isclose(n_length, 1.0, rel_tol=1e-5):
            raise ValueError(f"Invalid non-unit normal vector: length is {n_length}")
            
        v_rad = math.atan2(nx, ny)
        xy_mag = math.hypot(nx, ny)
        u_rad = math.atan2(xy_mag, nz)
        
        # Position vector relative to rotation center
        p = np.array([x, y, z + self.bed_center_z])
        
        cos_v = math.cos(v_rad)
        sin_v = math.sin(v_rad)
        R_v = np.array([
            [cos_v, -sin_v, 0],
            [sin_v,  cos_v, 0],
            [0,      0,     1]
        ])
        
        cos_u = math.cos(u_rad)
        sin_u = math.sin(u_rad)
        R_u = np.array([
            [1, 0,      0],
            [0, cos_u, -sin_u],
            [0, sin_u,  cos_u]
        ])
        
        R_total = R_u @ R_v
        p_rotated = R_total @ p
        
        machine_x = float(p_rotated[0])
        machine_y = float(p_rotated[1])
        machine_z = float(p_rotated[2] - self.bed_center_z)
        
        u_deg = math.degrees(u_rad)
        v_deg = math.degrees(v_rad)
        
        return machine_x, machine_y, machine_z, {'u': u_deg, 'v': v_deg}
