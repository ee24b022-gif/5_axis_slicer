import pytest
import trimesh
from slice_plane_model import SlicePlane
from enums import AngleUnit, RotationConvention
from chunk_builder import build_capped_chunks

@pytest.fixture
def cube_mesh():
    # A 20x20x20 cube sitting on the origin Z=0, centered at X=0, Y=0
    return trimesh.creation.box(extents=(20, 20, 20), transform=trimesh.transformations.translation_matrix([0, 0, 10]))

def create_horizontal_plane(z_height):
    return SlicePlane(
        plane_origin=(0, 0, z_height),
        unit_normal=(0, 0, 1),
        angle_pair=(0, 0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=(1, 0, 0),
        local_y=(0, 1, 0)
    )

def test_chunk_count_and_order(cube_mesh):
    # Two planes, should yield 3 chunks (Chunk 0, Chunk 1, Chunk 2)
    p1 = create_horizontal_plane(15)
    p2 = create_horizontal_plane(10)
    
    chunks = build_capped_chunks(cube_mesh, [p1, p2])
    
    assert len(chunks) == 3
    assert chunks[0] is not None
    assert chunks[1] is not None
    assert chunks[2] is not None
    
    # Chunk 0 should be the original mesh (z goes 0 to 20)
    assert abs(chunks[0].bounds[1][2] - 20.0) < 1e-4

def test_capped_geometry(cube_mesh):
    # Slice the cube at Z=10. The result should be the top half (Z=10 to Z=20).
    # Since normal is (0,0,1), it keeps the positive side (Z >= 10).
    p1 = create_horizontal_plane(10)
    
    chunks = build_capped_chunks(cube_mesh, [p1])
    chunk = chunks[1]
    
    # Must be watertight (capped)
    assert chunk.is_watertight
    # Bounding box should reflect Z in [10, 20]
    assert abs(chunk.bounds[0][2] - 10.0) < 1e-4
    assert abs(chunk.bounds[1][2] - 20.0) < 1e-4

def test_empty_chunk_explicit(cube_mesh):
    # A plane way above the cube
    p1 = create_horizontal_plane(100)
    
    chunks = build_capped_chunks(cube_mesh, [p1])
    
    assert len(chunks) == 2
    # Since the plane is at Z=100 and normal is +Z, the positive side is empty
    assert chunks[1] is None
