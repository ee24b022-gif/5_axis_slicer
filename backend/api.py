from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import math
import trimesh
import io
import os
import json
import uuid
import subprocess

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
async def slice_stl(
    file: UploadFile = File(...),
    line_width: float = Form(...),
    bed_center_z: float = Form(...),
    resolution: float = Form(1.0)
):
    try:
        contents = await file.read()
        mesh = trimesh.load(io.BytesIO(contents), file_type='stl')
        
        # Center mesh and export to temp file
        min_b, max_b = mesh.bounds
        center_x = (min_b[0] + max_b[0]) / 2.0
        center_y = (min_b[1] + max_b[1]) / 2.0
        min_z = min_b[2]
        mesh.apply_translation([-center_x, -center_y, -min_z])
        
        tmp_stl = f"/tmp/mesh_{uuid.uuid4().hex}.stl"
        mesh.export(tmp_stl)
        
        # Call C++ Slicer Engine
        cmd = ["./slicer_engine", tmp_stl, str(line_width), str(resolution), str(bed_center_z)]
        if not os.path.exists("./slicer_engine"):
            # Fallback compile just in case
            subprocess.run(["g++", "-O3", "-o", "slicer_engine", "slicer.cpp"], check=True)
            
        process = subprocess.run(cmd, capture_output=True, text=True)
        os.remove(tmp_stl)
        
        if process.returncode != 0:
            raise ValueError(f"C++ Engine failed: {process.stderr}")
            
        result = json.loads(process.stdout)
        if "error" in result:
            raise ValueError(result["error"])
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files from the built frontend
frontend_dist = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
