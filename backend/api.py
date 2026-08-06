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
    resolution: float = Form(1.0)
):
    try:
        contents = await file.read()
        
        tmp_stl = f"/tmp/mesh_{uuid.uuid4().hex}.stl"
        with open(tmp_stl, "wb") as f:
            f.write(contents)
        
        # Call C++ Slicer Engine (Centering is now done in C++)
        cmd = ["./slicer_engine", tmp_stl, str(line_width), str(resolution), str(bed_center_z)]
        if not os.path.exists("./slicer_engine"):
            # Fallback compile just in case
            subprocess.run(["g++", "-std=c++17", "-O0", "-o", "slicer_engine", "slicer.cpp"], check=True)
            
        if os.path.exists("./slicer_engine"):
            os.chmod("./slicer_engine", 0o755)
            
        process = subprocess.run(cmd, capture_output=True, text=True)
        os.remove(tmp_stl)
        
        if process.returncode != 0:
            raise HTTPException(status_code=400, detail=f"C++ Engine failed (Code {process.returncode}): {process.stderr}")
            
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=f"Invalid JSON from C++ engine. Output: {process.stdout[:100]}")
            
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files from the built frontend
frontend_dist = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
