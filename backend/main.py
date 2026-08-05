import argparse
from toolpath import generate_spiral_toolpath_on_hemisphere
from kinematics import Kinematics5Axis
from gcode import GCodeGenerator

def main():
    parser = argparse.ArgumentParser(description="Open5x Conformal Slicer")
    parser.add_argument("--radius", type=float, default=20.0, help="Radius of hemisphere")
    parser.add_argument("--line_width", type=float, default=0.4, help="Width of extrusion line")
    parser.add_argument("--bed_center_z", type=float, default=50.0, help="Distance from rotation center to bed surface")
    args = parser.parse_args()

    print(f"Generating toolpath for hemisphere (R={args.radius})...")
    path = generate_spiral_toolpath_on_hemisphere(args.radius, args.line_width)
    
    print("Initializing Kinematics and G-code Generator...")
    kinematics = Kinematics5Axis(bed_center_z=args.bed_center_z)
    generator = GCodeGenerator(e_multiplier=0.05, base_feedrate=1200)
    
    print("Processing IK and generating G-code...")
    gcode = generator.generate(path, kinematics)
    
    out_file = "output.gcode"
    with open(out_file, "w") as f:
        f.write(gcode)
        
    print(f"Done! G-code saved to {out_file}")
    
if __name__ == "__main__":
    main()
