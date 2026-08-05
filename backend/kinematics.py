import numpy as np

class Kinematics5Axis:
    def __init__(self, bed_center_z=0.0):
        """
        Table-Table kinematics (Open5x).
        Assuming U (tilt) rotates around X axis.
        Assuming V (rotate) rotates around Z axis.
        bed_center_z: the Z distance from the rotation center to the print bed surface.
        """
        self.bed_center_z = bed_center_z

    def calculate_ik(self, x, y, z, nx, ny, nz):
        """
        Convert position and tool orientation normal to machine axes.
        (nx, ny, nz) points *away* from the surface. The tool needs to align with this normal.
        In the machine's reference frame, the tool points straight down (0, 0, -1).
        So the surface normal needs to point straight up (0, 0, 1) after table rotations.
        
        Returns:
            machine_x, machine_y, machine_z, u_deg, v_deg
        """
        # 1. Find the necessary bed rotations to align the normal with Z-axis
        # V rotation (around Z) aligns the normal's XY projection to the YZ plane.
        # U rotation (around X) tilts the normal to the Z axis.
        
        # Calculate V (rotation around Z)
        # We want the normal to lie in the YZ plane so we can tilt it around X.
        # So we rotate by V such that nx becomes 0.
        v_rad = np.arctan2(nx, ny)
        
        # Calculate U (tilt around X)
        # After V rotation, the normal is (0, ny', nz).
        # We want to tilt it around X by U so it becomes (0, 0, 1).
        # nz is the z-component, and sqrt(nx^2 + ny^2) is the y'-component.
        xy_mag = np.sqrt(nx**2 + ny**2)
        u_rad = np.arctan2(xy_mag, nz)
        
        # Apply the rotations to the part coordinates to find the required nozzle position.
        # The part is attached to the V table, which is attached to the U table.
        # Part -> V-rotation -> U-rotation -> Machine
        
        # Position vector relative to rotation center
        p = np.array([x, y, z + self.bed_center_z])
        
        # Rotation matrices
        # Forward rotation of the table (to find where the point goes)
        # Ry and Rx depends on the actual physical setup.
        # Standard: V rotates part around Z by V. U rotates part around X by U.
        
        cos_v = np.cos(v_rad)
        sin_v = np.sin(v_rad)
        R_v = np.array([
            [cos_v, -sin_v, 0],
            [sin_v,  cos_v, 0],
            [0,      0,     1]
        ])
        
        cos_u = np.cos(u_rad)
        sin_u = np.sin(u_rad)
        R_u = np.array([
            [1, 0,      0],
            [0, cos_u, -sin_u],
            [0, sin_u,  cos_u]
        ])
        
        # Combine rotations
        R_total = R_u @ R_v
        
        # Rotated position
        p_rotated = R_total @ p
        
        # Shift back from rotation center
        machine_x = p_rotated[0]
        machine_y = p_rotated[1]
        machine_z = p_rotated[2] - self.bed_center_z
        
        # Convert to degrees
        u_deg = np.degrees(u_rad)
        v_deg = np.degrees(v_rad)
        
        return machine_x, machine_y, machine_z, u_deg, v_deg
