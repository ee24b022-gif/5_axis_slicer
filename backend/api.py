from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import io
import os
import json
import uuid
import subprocess

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
    layer_height: float = Form(0.2),
    wave_amplitude: float = Form(0.0),
    wave_frequency: float = Form(0.1),
    infill_density: float = Form(20.0)
):
    try:
        contents = await file.read()
        from slicer_python import slice_mesh
        result = slice_mesh(contents, layer_height, bed_center_z, wave_amplitude, wave_frequency, infill_density)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files from the built frontend
frontend_dist = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
os.makedirs(frontend_dist, exist_ok=True)
index_path = os.path.join(frontend_dist, "index.html")
if not os.path.exists(index_path):
    with open(index_path, "w") as f:
        f.write("<html><body>Frontend is served by Vercel. This is the API server.</body></html>")

app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
