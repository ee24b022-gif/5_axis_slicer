import numpy as np
import trimesh

if __name__ == "__main__":
    # Create a simple L-bracket shape
    base = trimesh.creation.box(extents=[20, 20, 20])
    base.apply_translation([0, 0, 10])

    overhang = trimesh.creation.box(extents=[40, 20, 10])
    overhang.apply_translation([20, 0, 25])

    mesh = trimesh.util.concatenate([base, overhang])
    mesh.export('test_overhang_auto.stl')
    print("Generated test_overhang_auto.stl")
