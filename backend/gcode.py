import math

class GCodeGenerator:
    def __init__(self, e_multiplier=0.05, base_feedrate=1500, retract_distance=2.0,
                 travel_feedrate=3000, retract_feedrate=2400, travel_threshold=1.5):
        """
        e_multiplier:      mm of filament per mm of part travel
        base_feedrate:     nominal print feedrate (mm/min)
        retract_distance:  filament retraction length on travel moves (mm)
        travel_feedrate:   rapid move feedrate (mm/min)
        retract_feedrate:  retract/unretract feedrate (mm/min)
        travel_threshold:  part-space distance (mm) above which a move is considered
                           a travel (non-printing) move and triggers retraction
        """
        self.e_multiplier = e_multiplier
        self.base_feedrate = base_feedrate
        self.retract_distance = retract_distance
        self.travel_feedrate = travel_feedrate
        self.retract_feedrate = retract_feedrate
        self.travel_threshold = travel_threshold

        self.current_v = 0.0
        self.current_e = 0.0
        self.last_pos = None
        self._retracted = False  # track whether filament is currently retracted

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

    def _retract(self, gcode):
        """Append a retract command and mark state as retracted."""
        if not self._retracted:
            gcode.append(f"G1 E{self.current_e - self.retract_distance:.3f} F{self.retract_feedrate:.0f} ; Retract")
            self._retracted = True

    def _unretract(self, gcode):
        """Append an unretract command and clear the retracted state."""
        if self._retracted:
            gcode.append(f"G1 E{self.current_e:.3f} F{self.retract_feedrate:.0f} ; Unretract")
            self._retracted = False

    def generate(self, path_points, kinematics, path_ids=None):
        """
        path_points: list of (x, y, z, nx, ny, nz)

        BUG FIX (Bug 4): Original code had no retract/unretract logic.
        Filament was continuously extruded even during travel moves (large
        jumps between disconnected path segments), causing ooze blobs and
        material deposited in mid-air.  Now we detect travel moves by
        comparing the part-space distance between consecutive points against
        `travel_threshold`, retract before the travel, and unretract after.
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
            current_path_id = path_ids[i] if path_ids else 0
            mx, my, mz, mu, mv = kinematics.calculate_ik(x, y, z, nx, ny, nz)

            mv_optimized = self.optimize_v_rotation(mv)

            if self.last_pos is None:
                # First point: travel to start position without extruding
                gcode.append(f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} U{mu:.3f} V{mv_optimized:.3f} F{self.travel_feedrate:.0f}")
                self.last_pos = (mx, my, mz, mu, mv_optimized, x, y, z, current_path_id)
                continue

            last_mx, last_my, last_mz, last_mu, last_mv, last_x, last_y, last_z, last_path_id = self.last_pos

            # Distance the nozzle travels relative to the part (determines extrusion)
            dist_part = math.sqrt((x - last_x)**2 + (y - last_y)**2 + (z - last_z)**2)

            # Distance the machine axes physically move (used for feedrate scaling)
            dist_mach = math.sqrt(
                (mx - last_mx)**2 + (my - last_my)**2 + (mz - last_mz)**2 +
                (mu - last_mu)**2 + (mv_optimized - last_mv)**2
            )

            if dist_part > self.travel_threshold or (path_ids and current_path_id != last_path_id):
                # --- TRAVEL MOVE: retract, rapid travel, unretract ---
                self._retract(gcode)
                gcode.append(
                    f"G0 X{mx:.3f} Y{my:.3f} Z{mz:.3f} "
                    f"U{mu:.3f} V{mv_optimized:.3f} F{self.travel_feedrate:.0f} ; Travel"
                )
                self._unretract(gcode)
            else:
                # --- PRINT MOVE: extrude proportional to part distance ---
                if dist_part > 1e-6:  # guard against zero-length moves
                    extrusion = dist_part * self.e_multiplier
                    self.current_e += extrusion

                    # Scale feedrate so nozzle moves at base_feedrate over the part.
                    # If machine axes travel further (e.g. rotary axis), feedrate is
                    # increased proportionally to maintain constant part-speed.
                    if dist_part > 0:
                        feedrate = self.base_feedrate * (dist_mach / dist_part)
                    else:
                        feedrate = self.base_feedrate

                    # Clamp to safe mechanical limits
                    max_feedrate = 6000
                    feedrate = min(feedrate, max_feedrate)

                    gcode.append(
                        f"G1 X{mx:.3f} Y{my:.3f} Z{mz:.3f} "
                        f"U{mu:.3f} V{mv_optimized:.3f} "
                        f"E{self.current_e:.3f} F{feedrate:.1f}"
                    )

            self.last_pos = (mx, my, mz, mu, mv_optimized, x, y, z, current_path_id)

        return "\n".join(gcode)

