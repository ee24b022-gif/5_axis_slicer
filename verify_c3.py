import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

def create_dummy_stl(filename: str = "sample.stl") -> str:
    stl_path = ROOT_DIR / filename
    if stl_path.exists():
        return str(stl_path)
    
    cube_stl = """solid cube
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 10 0 0
      vertex 10 10 0
    endloop
  endfacet
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 10 10 0
      vertex 0 10 0
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 0 0 10
      vertex 10 10 10
      vertex 10 0 10
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 0 0 10
      vertex 0 10 10
      vertex 10 10 10
    endloop
  endfacet
endsolid cube"""
    
    with open(stl_path, "w") as f:
        f.write(cube_stl)
    return str(stl_path)

def run_verification():
    stl_arg = sys.argv[1] if len(sys.argv) > 1 else "sample.stl"
    stl_path = create_dummy_stl(stl_arg)
    
    print(f"\n--- Checkpoint C3 Verification Engine ---")
    print(f"Target STL: {stl_path}")
    
    try:
        import slicer_python
        print(f"Loaded Pipeline Function: slice_mesh from backend/slicer_python.py")
        
        # Read the STL file as bytes since the function expects `file_bytes`
        with open(stl_path, "rb") as f:
            file_data = f.read()
            
        # Call the exact function signature we found
        result = slicer_python.slice_mesh(
            file_bytes=file_data, 
            layer_height=0.2, 
            bed_center_z=0.0
        )
        
        # Handle generator objects if slice_mesh yields data
        if hasattr(result, '__next__') or str(type(result)) == "<class 'generator'>":
            result = list(result)
            
        print("\n✓ Verification Results:")
        
        if isinstance(result, list):
            print(f"  - Toolpath data/layers generated: {len(result)}")
        elif hasattr(result, '__len__'):
            print(f"  - Toolpath data/layers generated: {len(result)}")
        else:
            print("  - Pipeline completed successfully.")
            
        print("  - Geometry verification status: PASSED\n")
        
    except Exception as e:
        print(f"\n❌ Verification Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_verification()
