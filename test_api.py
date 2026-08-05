import asyncio
import io
import os
import uuid
import subprocess
import json
import trimesh

async def test_slice():
    # 1. Create a large dummy mesh to simulate a real STL
    print("Creating dummy mesh...")
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=10) # 20k triangles
    contents = mesh.export(file_type='stl') # Binary STL
    print(f"Mesh size: {len(contents)} bytes")
    
    # 2. Simulate API logic
    tmp_stl = f"test_mesh_{uuid.uuid4().hex}.stl"
    with open(tmp_stl, "wb") as f:
        f.write(contents)
        
    line_width = 0.4
    resolution = 1.0
    bed_center_z = 50.0
    
    cmd = ["./slicer_engine", tmp_stl, str(line_width), str(resolution), str(bed_center_z)]
    
    print("Running C++ slicer...")
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print("C++ slicer finished.")
        if process.returncode != 0:
            print(f"ERROR: {process.stderr}")
        else:
            try:
                res = json.loads(process.stdout)
                print(f"SUCCESS! Points generated: {len(res.get('toolpath_points', []))}")
            except Exception as e:
                print(f"JSON Parse Error: {e}")
                print(f"Stdout prefix: {process.stdout[:100]}")
    except subprocess.TimeoutExpired:
        print("TIMEOUT: C++ engine hung!")
        
    if os.path.exists(tmp_stl):
        os.remove(tmp_stl)

asyncio.run(test_slice())
