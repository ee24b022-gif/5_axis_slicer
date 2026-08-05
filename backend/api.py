from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math

# Import our existing slicer modules
from toolpath import generate_spiral_toolpath_on_hemisphere
from kinematics import Kinematics5Axis
from gcode import GCodeGenerator

app = FastAPI(title="Open5x Slicer API")

# Allow CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SliceRequest(BaseModel):
    radius: float = 20.0
    line_width: float = 0.4
    bed_center_z: float = 50.0

@app.post("/slice")
def slice_model(request: SliceRequest):
    try:
        # Generate toolpath
        path = generate_spiral_toolpath_on_hemisphere(request.radius, request.line_width)
        
        # Initialize IK and GCode Generator
        kinematics = Kinematics5Axis(bed_center_z=request.bed_center_z)
        generator = GCodeGenerator(e_multiplier=0.05, base_feedrate=1200)
        
        # Generate G-code
        gcode = generator.generate(path, kinematics)
        
        # For visualization on the frontend, we can also return the 3D points
        # to render the toolpath lines.
        points_3d = [{"x": p[0], "y": p[1], "z": p[2]} for p in path]
        
        return {
            "gcode": gcode,
            "toolpath_points": points_3d
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Open5x Slicer API is running!"}
