from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import trimesh
import io

from toolpath import generate_zig_zag_toolpath_on_mesh
from kinematics import Kinematics5Axis
from gcode import GCodeGenerator

app = FastAPI(title="Open5x Slicer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/slice_stl")
async def slice_stl(file: UploadFile = File(...), line_width: float = Form(0.4), bed_center_z: float = Form(50.0)):
    try:
        contents = await file.read()
        mesh = trimesh.load(io.BytesIO(contents), file_type='stl')
        
        min_b, max_b = mesh.bounds
        center_x = (min_b[0] + max_b[0]) / 2.0
        center_y = (min_b[1] + max_b[1]) / 2.0
        min_z = min_b[2]
        mesh.apply_translation([-center_x, -center_y, -min_z])
        
        path = generate_zig_zag_toolpath_on_mesh(mesh, line_width)
        if not path:
            raise ValueError("Failed to generate path. Mesh might be invalid or too small.")
            
        kinematics = Kinematics5Axis(bed_center_z=bed_center_z)
        generator = GCodeGenerator(e_multiplier=0.05, base_feedrate=1200)
        gcode = generator.generate(path, kinematics)
        points_3d = [{"x": p[0], "y": p[1], "z": p[2]} for p in path]
        
        return {"gcode": gcode, "toolpath_points": points_3d}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Open5x Slicer API is running!"}
