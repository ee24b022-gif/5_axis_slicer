import math
from dialect_model import DialectSettings

class RotaryGCodeGenerator:
    """
    5-axis aware G-code generator.
    Relies entirely on verified machine adapters to compute rotary angles,
    and strongly-typed DialectSettings to map them to physical axes.
    Rejects any unverified configurations before generation.
    """
    def __init__(self, settings: DialectSettings, kinematics_adapter, e_multiplier=0.05, travel_threshold=1.5):
        self.settings = settings
        self.kinematics = kinematics_adapter
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
        
        # We need to compute the first point to verify the adapter's rotary mapping exists in our dialect
        if not path_points:
            return "", {"is_prototype": True, "rotary_enabled": True, "axes": []}
            
        test_pt = path_points[0]
        # Depending on the adapter (TableTable vs Fractal) we pass nx/ny/nz or just a LogicalPose
        # For this refactor, we stick to the common calculate_ik footprint of TableTableUVAdapter.
        _, _, _, rotary_dict = self.kinematics.calculate_ik(*test_pt)
        
        # Verify that EVERY rotary axis output by the adapter is explicitly defined in our axis mapping
        for rot_axis in rotary_dict.keys():
            if rot_axis not in self.settings.axis_mapping:
                raise ValueError(f"Unverified mapping: adapter generated rotary axis '{rot_axis}' not defined in dialect mapping.")
                
        # Header sequence
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
            x, y, z, nx, ny, nz = pt
            current_path_id = path_ids[i] if path_ids else 0
            
            mx, my, mz, rotary_dict = self.kinematics.calculate_ik(x, y, z, nx, ny, nz)
            
            # Format the rotary string part
            if self.settings.dialect == "klipper_manual_stepper_ab":
                rotary_cmds = [f"MANUAL_STEPPER STEPPER=stepper_{k.lower()} POS={v:.3f}" for k, v in rotary_dict.items()]
                rotary_str = "\n" + "\n".join(rotary_cmds) if rotary_cmds else ""
            else:
                rotary_str = " " + " ".join([f"{self.settings.axis_mapping[k]}{v:.3f}" for k, v in rotary_dict.items()]) if rotary_dict else ""
            
            if self.last_pos is None:
                gcode.append(f"G0 {x_ax}{mx:.3f} {y_ax}{my:.3f} {z_ax}{mz:.3f} F{self.settings.feed_limits.travel:.0f}{rotary_str}")
                self.last_pos = (mx, my, mz, rotary_dict, x, y, z, current_path_id)
                continue
                
            last_mx, last_my, last_mz, last_rotary_dict, last_x, last_y, last_z, last_path_id = self.last_pos
            
            dist_part = math.hypot(x - last_x, y - last_y, z - last_z)
            
            if dist_part > self.travel_threshold or (path_ids and current_path_id != last_path_id):
                self._retract(gcode)
                gcode.append(f"G0 {x_ax}{mx:.3f} {y_ax}{my:.3f} {z_ax}{mz:.3f} F{self.settings.feed_limits.travel:.0f} ; Travel{rotary_str}")
                self._unretract(gcode)
            else:
                if dist_part > 1e-6:
                    extrusion = dist_part * self.e_multiplier
                    self.current_e += extrusion
                    
                    # Normalize feedrate across all physically traveling axes (simplified)
                    feedrate = self.settings.feed_limits.print
                    gcode.append(f"G1 {x_ax}{mx:.3f} {y_ax}{my:.3f} {z_ax}{mz:.3f} {e_ax}{self.current_e:.3f} F{feedrate:.1f}{rotary_str}")
                    
            self.last_pos = (mx, my, mz, rotary_dict, x, y, z, current_path_id)
            
        gcode.extend(self.settings.footer)
        
        metadata = {
            "is_prototype": True,
            "rotary_enabled": True,
            "axes": [self.settings.axis_mapping.get('x', 'X'), self.settings.axis_mapping.get('y', 'Y'), self.settings.axis_mapping.get('z', 'Z')] + 
                    [self.settings.axis_mapping[k] for k in rotary_dict.keys()]
        }
        
        return "\n".join(gcode), metadata
