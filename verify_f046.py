import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import trimesh

try:
    import transform_utils
    from auto_segment import AutoSegmenter
    print("✅ Backend modules loaded successfully.")
except ImportError as e:
    print(f"❌ Could not import backend modules: {e}")
    sys.exit(1)

canonical_fn = getattr(transform_utils, 'apply_canonical_transform', None)

def verify_f046():
    stl_path = "sample.stl"
    
    if os.path.exists(stl_path):
        print(f"📦 Loading {stl_path}...")
        mesh = trimesh.load(stl_path)
    else:
        print("⚠️ sample.stl not found in root, generating fallback test cube...")
        mesh = trimesh.creation.box(extents=(20, 20, 20))

    print(f"Mesh loaded: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces.")

    # 1. Apply canonical bed transform and unpack tuple if needed
    aligned_mesh = mesh
    if canonical_fn:
        try:
            res = canonical_fn(mesh)
            aligned_mesh = res[0] if isinstance(res, tuple) else res
            print("✅ Canonical bed alignment applied successfully.")
        except Exception as e:
            print(f"❌ Failed during bed alignment: {e}")
            return

    # 2. Run F-046 Auto-Segmentation via compute_segmentation
    try:
        segmenter = AutoSegmenter()
        
        if hasattr(segmenter, 'compute_segmentation'):
            phases = segmenter.compute_segmentation(aligned_mesh)
            print(f"✅ Auto-segmentation completed via 'compute_segmentation()'. Output generated: {len(phases)} phase(s).")
            for i, phase in enumerate(phases):
                print(f"   • Phase {i + 1}: {type(phase).__name__}")
        else:
            available_methods = [m for m in dir(segmenter) if not m.startswith('_')]
            print(f"⚠️ Target method not matched on AutoSegmenter. Available methods: {available_methods}")

    except Exception as e:
        print(f"❌ Failed during segmentation execution: {e}")

if __name__ == "__main__":
    verify_f046()