import pytest
import uuid
import trimesh
from chunk_builder import subtract_later_chunks

def test_successful_subtraction():
    # Chunk 0: a 20x20x20 box at origin
    chunk0 = trimesh.creation.box(extents=(20, 20, 20))
    # Chunk 1: a 20x20x20 box offset by (10, 0, 0)
    chunk1 = trimesh.creation.box(extents=(20, 20, 20), transform=trimesh.transformations.translation_matrix([10, 0, 0]))
    
    chunks = [chunk0.copy(), chunk1.copy()]
    
    job_id = str(uuid.uuid4())
    processed_chunks, diagnostics = subtract_later_chunks(job_id, chunks)
    
    # Chunk 0 should now be smaller in X (only covers X from -10 to 0)
    assert len(diagnostics) == 0
    assert processed_chunks[0] is not None
    assert processed_chunks[1] is not None
    
    bounds_x_max = processed_chunks[0].bounds[1][0]
    assert abs(bounds_x_max - 0.0) < 1e-4
    assert processed_chunks[0].is_watertight

def test_empty_chunk_classification():
    # Chunk 0 and Chunk 1 are mathematically identical.
    # Subtracting chunk 1 from chunk 0 should leave chunk 0 empty.
    chunk0 = trimesh.creation.box(extents=(20, 20, 20))
    chunk1 = trimesh.creation.box(extents=(20, 20, 20))
    
    chunks = [chunk0.copy(), chunk1.copy()]
    
    job_id = str(uuid.uuid4())
    processed_chunks, diagnostics = subtract_later_chunks(job_id, chunks)
    
    # Chunk 0 is destroyed
    assert processed_chunks[0] is None
    assert processed_chunks[1] is not None
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "EMPTY_CHUNK_AFTER_SUBTRACTION"
