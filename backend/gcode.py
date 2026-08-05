import math

class GCodeGenerator:
    def __init__(self, e_multiplier=0.05, base_feedrate=1500):
        self.e_multiplier = e_multiplier
        self.base_feedrate = base_feedrate
        self.current_v = 0.0
        self.current_e = 0.0
        self.last_pos = None

    def optimize_v_rotation(self, target_v):
        """
        Optimizes the bed rotation to take the shortest path.
        For example, going from 355 to 1 degree should be +6 degrees, not -354.
        """
        # Normalize current_v to 0-360 range
        current_mod = self.current_v % 360
        target_mod = target_v % 360
        
        diff = target_mod - current_mod
        if diff > 180:
            diff -= 360
        elif diff < -180:
            diff += 360
            
        self.current_v += diff
        return self.current_v

    def generate(self, path_points, kinematics):
        """
        path_points: list of (x, y, z, nx, ny, nz)
        """
        gcode = [
            "; Open5x Conformal Slicer Output",
            "G21 ; Set units to millimeters",
            "G90 ; Absolute positioning",
            "M82 ; Absolute extrusion mode",
            "; Setup initial temperatures and homing here",
            "G28 ; Home all axes",
            "G0 Z50 F3000 ; Move up to avoid collisions"
        ]
        
        for i, pt in enumerate(path_points):
            x, y, z, nx, ny, nz = pt
            mx, my, mz, mu, mv = kinematics.calculate_ik(x, y, z, nx, ny, nz)
            
            mv_optimized = self.optimize_v_rotation(mv)
            
            if self.last_pos is None:
                # First point, just travel
                gcode.append(f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv_optimized:.3f} F3000")
                self.last_pos = (mx, my, mz, mu, mv_optimized, x, y, z)
                continue
                
            last_mx, last_my, last_mz, last_mu, last_mv, last_x, last_y, last_z = self.last_pos
            
            # Distance relative to the part itself (Euclidean distance between original path points)
            dist_part = math.sqrt((x - last_x)**2 + (y - last_y)**2 + (z - last_z)**2)
            
            # Distance the machine axes actually move
            dist_mach = math.sqrt((mx - last_mx)**2 + (my - last_my)**2 + (mz - last_mz)**2 + (mu - last_mu)**2 + (mv_optimized - last_mv)**2)
            
            # Extrusion amount is proportional to the distance moved on the part
            extrusion = dist_part * self.e_multiplier
            self.current_e += extrusion
            
            # Speed optimization: The nozzle should move at `base_feedrate` relative to the part.
            # If the machine has to move further (e.g. rotary axis movement), we increase the feedrate.
            if dist_part > 0:
                feedrate = self.base_feedrate * (dist_mach / dist_part)
            else:
                feedrate = self.base_feedrate
                
            # Limit maximum feedrate to avoid mechanical limits
            max_feedrate = 6000
            feedrate = min(feedrate, max_feedrate)
            
            gcode.append(f"G1 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv_optimized:.3f} E{self.current_e:.3f} F{feedrate:.1f}")
            self.last_pos = (mx, my, mz, mu, mv_optimized, x, y, z)
            
        return "\n".join(gcode)
