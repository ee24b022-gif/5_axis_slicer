import re

with open('backend/geometry_service.py', 'r') as f:
    content = f.read()

# We want to wrap from `emit(JobStage.MESH_VALIDATION, 0.0)` to the end in a `try: ... except JobCancelledError:`
# Wait, it's easier to just do it via indentation.
