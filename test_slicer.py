import trimesh
import subprocess
import json

mesh = trimesh.creation.box([10, 10, 10])
mesh.export("test.stl")

subprocess.run(["g++", "-O3", "-o", "slicer_engine", "backend/slicer.cpp"], check=True)
process = subprocess.run(["./slicer_engine", "test.stl", "0.4", "1.0", "50.0"], capture_output=True, text=True)

if process.returncode != 0:
    print("FAILED")
    print(process.stderr)
else:
    print("SUCCESS")
    # Don't print the whole json, just the first 100 chars
    print(process.stdout[:100])
