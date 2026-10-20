"""
Tests for chunk_builder.py using manifold3d for watertight, volume-conserving
chunk production on tilted planes.

Covers pipe_fitting.stl with a two-plane configuration:
  - Horizontal plane at z=60
  - 30-degree tilted plane at z=90

Every chunk must be watertight, chunk volumes must sum to the mesh volume
within 0.1%, and no chunk may be None.
"""

import math
import os

import numpy as np
import pytest
import trimesh

from chunk_builder import build_capped_chunks, subtract_later_chunks
from slice_plane_model import SlicePlane

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PIPE_STL = os.path.join(FIXTURE_DIR, "pipe_fitting.stl")

_S3 = math.sqrt(3.0) / 2.0

PLANE_HORIZ_Z60 = {
    "plane_origin": (0.0, 0.0, 60.0),
    "unit_normal": (0.0, 0.0, 1.0),
    "angle_pair": (0.0, 0.0),
    "angle_units": "degrees",
    "rotation_convention": "AC_TABLE",
    "local_x": (1.0, 0.0, 0.0),
    "local_y": (0.0, 1.0, 0.0),
    "source_frame": "canonical",
}

PLANE_TILTED_Z90 = {
    "plane_origin": (0.0, 0.0, 90.0),
    "unit_normal": (0.5, 0.0, _S3),  # 30 deg tilt from vertical
    "angle_pair": (30.0, 90.0),
    "angle_units": "degrees",
    "rotation_convention": "AC_TABLE",
    "local_x": (0.0, 1.0, 0.0),
    "local_y": (-_S3, 0.0, 0.5),
    "source_frame": "canonical",
}


@pytest.fixture
def aligned_pipe():
    mesh = trimesh.load(PIPE_STL)
    assert mesh.is_watertight
    # Apply identity transform (pipe already in canonical frame for tests)
    # Use transform_utils if available, otherwise identity
    try:
        from transform_utils import apply_canonical_transform
        aligned, _ = apply_canonical_transform(mesh.copy())
    except Exception:
        aligned = mesh
    return aligned


def test_chunk_builder_two_plane_watertight_volume(aligned_pipe):
    """Two-plane config: every chunk watertight, volumes sum to mesh volume."""
    mesh = aligned_pipe
    mesh_vol = mesh.volume

    planes = [
        SlicePlane(**PLANE_HORIZ_Z60),
        SlicePlane(**PLANE_TILTED_Z90),
    ]

    chunks = build_capped_chunks(mesh, planes)
    assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"

    # No chunk may be None
    for i, c in enumerate(chunks):
        assert c is not None, f"Chunk {i} is None (plane missed or empty result)"

    # Subtract later chunks
    chunks2, diags = subtract_later_chunks("test", chunks)
    assert len(chunks2) == 3

    total_vol = 0.0
    for i, c in enumerate(chunks2):
        assert c is not None, f"Chunk {i} became None after subtraction"
        assert not c.is_empty, f"Chunk {i} is empty after subtraction"
        assert c.is_watertight, f"Chunk {i} is not watertight after subtraction"
        total_vol += c.volume

    # Volumes must sum to the original mesh volume within 0.1%
    rel_err = abs(total_vol - mesh_vol) / mesh_vol
    assert rel_err <= 0.001, (
        f"Chunk volumes {total_vol:.4f} deviate from mesh volume {mesh_vol:.4f} "
        f"(rel err {rel_err:.6f} > 0.001)"
    )


def test_chunk_builder_single_horizontal_plane(aligned_pipe):
    """Single horizontal plane: both chunks watertight, volumes sum correctly."""
    mesh = aligned_pipe
    mesh_vol = mesh.volume

    planes = [SlicePlane(**PLANE_HORIZ_Z60)]
    chunks = build_capped_chunks(mesh, planes)
    assert len(chunks) == 2

    for i, c in enumerate(chunks):
        assert c is not None, f"Chunk {i} is None"
        assert c.is_watertight, f"Chunk {i} is not watertight"

    chunks2, diags = subtract_later_chunks("test", chunks)
    total_vol = sum(c.volume for c in chunks2 if c is not None)
    rel_err = abs(total_vol - mesh_vol) / mesh_vol
    assert rel_err <= 0.001, (
        f"Chunk volumes {total_vol:.4f} deviate from mesh volume {mesh_vol:.4f} "
        f"(rel err {rel_err:.6f} > 0.001)"
    )


def test_chunk_builder_no_planes(aligned_pipe):
    """No planes: single chunk = whole mesh, watertight."""
    mesh = aligned_pipe
    chunks = build_capped_chunks(mesh, [])
    assert len(chunks) == 1
    assert chunks[0] is not None
    assert chunks[0].is_watertight
    assert abs(chunks[0].volume - mesh.volume) / mesh.volume < 1e-6


def test_chunk_builder_plane_misses_mesh(aligned_pipe):
    """Plane far above mesh: chunk for that plane is None."""
    mesh = aligned_pipe
    far_plane = {
        "plane_origin": (0.0, 0.0, 100000.0),
        "unit_normal": (0.0, 0.0, 1.0),
        "angle_pair": (0.0, 0.0),
        "angle_units": "degrees",
        "rotation_convention": "AC_TABLE",
        "local_x": (1.0, 0.0, 0.0),
        "local_y": (0.0, 1.0, 0.0),
        "source_frame": "canonical",
    }
    planes = [SlicePlane(**far_plane)]
    chunks = build_capped_chunks(mesh, planes)
    assert len(chunks) == 2
    # Chunk 0 = whole mesh (below far plane), chunk 1 = nothing above it
    assert chunks[0] is not None
    assert chunks[1] is None, f"Expected chunk 1 to be None (plane missed mesh), got {chunks[1]}"
