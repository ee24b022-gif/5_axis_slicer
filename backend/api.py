from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import io
import os
import json
import uuid
import subprocess
import asyncio
from slicer_python import slice_mesh

app = FastAPI(title="Open5x Slicer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/slice_stl")
async def slice_stl_endpoint(
    file: UploadFile = File(...), 
    layer_height: float = Form(0.2), 
    bed_center_z: float = Form(100.0),
    wave_amplitude: float = Form(0.0),
    wave_frequency: float = Form(0.1),
    infill_density: float = Form(20.0),
    auto_segment: bool = Form(False),
    model_scale: float = Form(1.0),
    rot_x: float = Form(0.0),
    rot_y: float = Form(0.0),
    rot_z: float = Form(0.0),
    pos_x: float = Form(0.0),
    pos_y: float = Form(0.0),
    infill_pattern: str = Form("lines")
):
    try:
        contents = await file.read()
        loop = asyncio.get_running_loop()
        
        # Run CPU-bound slicing in a thread pool
        result = await loop.run_in_executor(
            None, 
            slice_mesh, 
            contents, 
            layer_height, 
            bed_center_z,
            wave_amplitude,
            wave_frequency,
            infill_density,
            auto_segment,
            model_scale,
            rot_x,
            rot_y,
            rot_z,
            pos_x,
            pos_y,
            infill_pattern
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
            
        def stream_response():
            try:
                # 1. Segmentation Info
                seg_json = json.dumps(result["segmentation_info"])
                yield f'{{"segmentation_info": {seg_json}, "toolpath_points": {{'
                
                # 2. Toolpath Points (Array streaming)
                pts = result["toolpath_points"]
                for key, arr in pts.items():
                    yield f'"{key}": ['
                    chunk_size = 5000
                    for i in range(0, len(arr), chunk_size):
                        chunk = arr[i:i+chunk_size]
                        if key in ('x', 'y', 'z'):
                            s = ",".join(f"{v:.2f}" for v in chunk)
                        else:
                            s = ",".join(str(v) for v in chunk)
                        if i > 0 and s: yield ","
                        yield s
                    yield ']'
                    if key != "type": yield ','
                yield '}, "gcode": "'
                
                # 3. GCode streaming
                gcode_file = result["gcode_file"]
                gcode_file.seek(0)
                while True:
                    chunk = gcode_file.read(65536)
                    if not chunk: break
                    yield chunk.replace('\n', '\\n').replace('"', '\\"')
                yield '"}'
                
            finally:
                if "gcode_file" in result:
                    result["gcode_file"].close()

        return StreamingResponse(stream_response(), media_type="application/json")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files from the built frontend
frontend_dist = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
os.makedirs(frontend_dist, exist_ok=True)
index_path = os.path.join(frontend_dist, "index.html")
if not os.path.exists(index_path):
    with open(index_path, "w") as f:
        f.write("<html><body>Frontend is served by Vercel. This is the API server.</body></html>")

app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
