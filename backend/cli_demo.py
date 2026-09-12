import argparse
from toolpath import generate_spiral_toolpath_on_hemisphere
from uv_adapter import TableTableUVAdapter
from rotary_gcode import RotaryGCodeGenerator
from dialect_model import DialectSettings, FeedLimits, RetractionSettings
from enums import GCodeDialect, CoordinateMode

def main():
    parser = argparse.ArgumentParser(description="Open5x Conformal Slicer")
    parser.add_argument("--radius", type=float, default=20.0, help="Radius of hemisphere")
    parser.add_argument("--line_width", type=float, default=0.4, help="Width of extrusion line")
    parser.add_argument("--bed_center_z", type=float, default=50.0, help="Distance from rotation center to bed surface")
    args = parser.parse_args()

    print(f"Generating toolpath for hemisphere (R={args.radius})...")
    path = generate_spiral_toolpath_on_hemisphere(args.radius, args.line_width)
    
    print("Initializing Kinematics and G-code Generator...")
    settings = DialectSettings(
        dialect=GCodeDialect.MARLIN,
        coordinate_mode=CoordinateMode.ABSOLUTE,
        units="mm",
        axis_mapping={"x": "X", "y": "Y", "z": "Z", "e": "E", "u": "U", "v": "V"},
        feed_limits=FeedLimits(travel=3000, print=1500, retract=2400),
        retraction=RetractionSettings(distance=2.0, feedrate=2400),
        clearance_moves=["G0 Z50 F3000"],
        header=["; START"],
        footer=["; END"],
        provenance_enabled=True
    )
    kinematics = TableTableUVAdapter(bed_center_z=args.bed_center_z)
    generator = RotaryGCodeGenerator(settings, kinematics, e_multiplier=0.05, travel_threshold=1.5)
    
    print("Processing IK and generating G-code...")
    gcode, metadata = generator.generate(path)
    
    out_file = "output.gcode"
    with open(out_file, "w") as f:
        f.write(gcode)
        
    print(f"Done! G-code saved to {out_file}")
    
if __name__ == "__main__":
    main()
