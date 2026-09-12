import math
from dialect_model import DialectSettings

class ThreeAxisGCodeGenerator:
    """
    Strict 3-axis G-code generator.
    Enforces that absolutely no rotary commands (A, B, C, U, V, W) can be emitted.
    Relies on DialectSettings to validate and supply physical boundaries.
    """
    def __init__(self, settings: DialectSettings, e_multiplier=0.05, travel_threshold=1.5):
        self.settings = settings
        self.e_multiplier = e_multiplier
        self.travel_threshold = travel_threshold
        
        self.current_e = 0.0
        self.last_pos = None
        self._retracted = False

    def _retract(self, gcode):
        if not self._retracted:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            gcode.append(f"G1 {e_axis}{self.current_e - self.settings.retraction.distance:.3f} F{self.settings.retraction.feedrate:.0f} ; Retract")
            self._retracted = True

    def _unretract(self, gcode):
        if self._retracted:
            e_axis = self.settings.axis_mapping.get('e', 'E')
            gcode.append(f"G1 {e_axis}{self.current_e:.3f} F{self.settings.retraction.feedrate:.0f} ; Unretract")
            self._retracted = False

    def generate(self, path_points, path_ids=None):
        gcode = []
        
        gcode.extend(self.settings.header)
        
        if self.settings.units == "mm":
            gcode.append("G21 ; Set units to millimeters")
            
        if self.settings.coordinate_mode.value == "absolute":
            gcode.append("G90 ; Absolute positioning")
            gcode.append("M82 ; Absolute extrusion mode")
            
        gcode.extend(self.settings.clearance_moves)

        x_ax = self.settings.axis_mapping.get('x', 'X')
        y_ax = self.settings.axis_mapping.get('y', 'Y')
        z_ax = self.settings.axis_mapping.get('z', 'Z')
        e_ax = self.settings.axis_mapping.get('e', 'E')
        
        for i, pt in enumerate(path_points):
            x, y = pt[0], pt[1]
            z = pt[2] if len(pt) > 2 else getattr(layer, "z_height", 0.0)
            current_path_id = path_ids[i] if path_ids else 0
            
            if self.last_pos is None:
                gcode.append(f"G0 {x_ax}{x:.3f} {y_ax}{y:.3f} {z_ax}{z:.3f} F{self.settings.feed_limits.travel:.0f}")
                self.last_pos = (x, y, z, current_path_id)
                continue
                
            last_x, last_y, last_z, last_path_id = self.last_pos
            
            dist = math.hypot(x - last_x, y - last_y, z - last_z)
            
            if dist > self.travel_threshold or (path_ids and current_path_id != last_path_id):
                self._retract(gcode)
                gcode.append(f"G0 {x_ax}{x:.3f} {y_ax}{y:.3f} {z_ax}{z:.3f} F{self.settings.feed_limits.travel:.0f} ; Travel")
                self._unretract(gcode)
            else:
                if dist > 1e-6:
                    extrusion = dist * self.e_multiplier
                    self.current_e += extrusion
                    
                    feedrate = self.settings.feed_limits.print
                    gcode.append(f"G1 {x_ax}{x:.3f} {y_ax}{y:.3f} {z_ax}{z:.3f} {e_ax}{self.current_e:.3f} F{feedrate:.1f}")
                    
            self.last_pos = (x, y, z, current_path_id)
            
        gcode.extend(self.settings.footer)
        return "\n".join(gcode)
