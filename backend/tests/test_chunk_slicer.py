import pytest
import trimesh
import numpy as np
from chunk_slicer import slice_chunk

def test_deterministic_chunk_slicing():
    # 1. Synthesize a 10x10x10 cube from Z=0 to Z=10
    cube = trimesh.creation.box(extents=(10, 10, 10))
    cube.apply_translation([0, 0, 5])
    
    chunk_idx = 1
    # Identity transform just to test retention
    transform = np.eye(4).flatten().tolist()
    
    # 2. Feed it into slice_chunk
    records = slice_chunk(
        mesh=cube,
        chunk_idx=chunk_idx,
        transform_matrix=transform,
        z_min=0.0,
        z_max=10.0,
        layer_height=1.0,
        first_layer_height=1.0,
        half_layer_offset=True
    )
    
    # Z schedule should be: 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5
    # That is exactly 10 layers.
    assert len(records) == 10
    
    # Iterate records
    for i, rec in enumerate(records):
        assert rec.chunk_idx == chunk_idx
        assert rec.layer_idx == i
        assert rec.transform_matrix == transform
        
        # Verify Z heights
        expected_z = 0.5 + float(i)
        assert abs(rec.z_height - expected_z) < 1e-4
        
        # Verify geometry
        segs = rec.segments
        # A 10x10 cube intersected by a plane returns a square.
        # It's constructed of 2 triangles per face generally, so it might output 4 or 8 segments.
        # But crucially, it's not empty!
        assert segs.shape[0] > 0
        assert segs.shape[1] == 2
        assert segs.shape[2] == 2
        
        # Check coordinates are bounded by the 10x10 size
        max_x = np.max(segs[:, :, 0])
        min_x = np.min(segs[:, :, 0])
        max_y = np.max(segs[:, :, 1])
        min_y = np.min(segs[:, :, 1])
        
        assert abs(max_x - 5.0) < 1e-4
        assert abs(min_x - (-5.0)) < 1e-4
        assert abs(max_y - 5.0) < 1e-4
        assert abs(min_y - (-5.0)) < 1e-4
