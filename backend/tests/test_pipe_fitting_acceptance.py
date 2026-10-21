"""
Acceptance tests for the pipe_fitting.stl geometry pipeline.

These tests exercise the slicing geometry primitives directly against
trimesh ground truth, bypassing the HTTP API:

* slice area reconstruction matches trimesh native sections
* the layer schedule length matches the expected layer count
* capped chunk volumes (partitioned) sum to the original mesh volume
* a nozzle swung into a tall part fails the job with a collision diagnostic
"""
import io
import math
import os

import numpy as np
import trimesh

import chunk_builder
import geometry_service
import layer_schedule
import polygonization
import slice_intersection
import transform_utils
from chunk_builder import subtract_later_chunks
from collision import CollisionEngine
from bvh import MeshBVH
from enums import AngleUnit, JobMode, RotationConvention
from geometry_service import GeometryApplicationService
from models import SlicerMachineProfile
from slice_plane_model import SlicePlane

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PIPE_FITTING_STL = os.path.join(FIXTURE_DIR, "pipe_fitting.stl")

# Bore heights where the pipe fitting has internal features.
BORE_HEIGHTS = (1.0, 10.0, 40.0, 80.0)


def _load_aligned_pipe_fitting() -> trimesh.Trimesh:
    """Load pipe_fitting.stl and place it canonically on the print bed."""
    mesh = trimesh.load(PIPE_FITTING_STL)
    aligned, _ = transform_utils.apply_canonical_transform(mesh)
    return aligned


def _make_horizontal_plane(z_height: float) -> SlicePlane:
    """Build a horizontal slice plane at the given Z height (+Z normal)."""
    return SlicePlane(
        plane_origin=(0.0, 0.0, z_height),
        unit_normal=(0.0, 0.0, 1.0),
        angle_pair=(0.0, 0.0),
        angle_units=AngleUnit.DEGREES,
        rotation_convention=RotationConvention.AC_TABLE,
        local_x=(1.0, 0.0, 0.0),
        local_y=(0.0, 1.0, 0.0),
    )


def _polygon_area(polygons) -> float:
    """Sum the area of a (possibly empty) MultiPolygon / Polygon result."""
    if polygons.is_empty:
        return 0.0
    if polygons.geom_type == "MultiPolygon":
        return sum(float(g.area) for g in polygons.geoms)
    return float(polygons.area)


def test_pipe_fitting_area_at_bore_heights():
    """Reconstructed slice areas must match trimesh native section areas.

    Compares the production chunk path
    (``slice_intersection.slice_mesh_at_z`` + ``polygonization.reconstruct_polygons``)
    against trimesh native sections at bore heights z = 1, 10, 40, 80 instead
    of evenly spaced sample heights.
    """
    aligned = _load_aligned_pipe_fitting()

    for z in BORE_HEIGHTS:
        z = float(z)

        # Production chunk path: slice the mesh, then reconstruct polygons.
        segments = slice_intersection.slice_mesh_at_z(aligned, z)
        polygons = polygonization.reconstruct_polygons(segments)
        computed_area = _polygon_area(polygons)

        # trimesh native section is ground truth.
        section = aligned.section(
            plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0]
        )
        if section is None or section.is_empty:
            continue
        truth_area = float(section.to_2D()[0].area)
        if truth_area == 0.0:
            # Nothing at this height: nothing to compare.
            continue

        rel_error = abs(computed_area - truth_area) / truth_area
        assert rel_error <= 0.005, (
            f"At z={z:.4f}: computed area {computed_area:.4f} "
            f"differs from trimesh section area {truth_area:.4f} "
            f"(relative error {rel_error:.4%} > 0.5%)"
        )


def test_pipe_fitting_layer_count():
    """The generated layer schedule length must match floor(height / h)."""
    aligned = _load_aligned_pipe_fitting()
    z_min = float(aligned.bounds[0][2])
    z_max = float(aligned.bounds[1][2])
    layer_height = 0.2

    schedule = layer_schedule.generate_layer_schedule(z_min, z_max, layer_height)
    expected = math.floor((z_max - z_min) / layer_height)

    assert abs(len(schedule) - expected) <= 1, (
        f"Expected about {expected} layers for z_min={z_min}, "
        f"z_max={z_max}, layer_height={layer_height}, got {len(schedule)}"
    )


def test_two_plane_chunk_volumes_sum_to_mesh_volume():
    """Partitioned capped chunk volumes must sum to the mesh volume."""
    mesh = trimesh.creation.box(
        extents=(20.0, 20.0, 20.0),
        transform=trimesh.transformations.translation_matrix([0.0, 0.0, 10.0]),
    )
    mesh_volume = float(mesh.volume)

    # Two horizontal planes: one at Z=10, one at Z=5 (both +Z normal).
    plane1 = _make_horizontal_plane(10.0)
    plane2 = _make_horizontal_plane(5.0)

    # build_capped_chunks returns [mesh, slice_above_plane1, slice_above_plane2];
    # the capped chunks overlap, so partition them (as the production
    # pipeline does in geometry_service) before summing volumes.
    chunks = chunk_builder.build_capped_chunks(mesh, [plane1, plane2])
    chunks, _diagnostics = subtract_later_chunks("test", chunks)

    total_volume = sum(
        float(c.volume) for c in chunks if c is not None
    )
    rel_error = abs(total_volume - mesh_volume) / mesh_volume
    assert rel_error <= 0.001, (
        f"Chunk volumes sum to {total_volume:.4f} but mesh volume is "
        f"{mesh_volume:.4f} (relative error {rel_error:.4%} > 0.1%)"
    )


def test_tall_column_collision_fails_job():
    """A nozzle swung into a tall column must fail the job with a collision diagnostic.

    A tall column (10x10 footprint, 100 tall, bottom on the bed at z in [0, 100])
    is sliced in THREE_AXIS mode with a machine profile of nozzle_length=3.0 and
    nozzle_holder_radius=5.0. At every layer above z=0 the holder sits 3mm above
    the tip with a 5mm radius, well within reach of the column wall below, so the
    job must fail with a collision error.
    """
    # Tall column: 10x10 footprint, 100 tall, bottom on the bed (z in [0, 100]).
    column = trimesh.creation.box(extents=(10.0, 10.0, 100.0))
    column.apply_translation([0.0, 0.0, 50.0])

    export_buf = io.BytesIO()
    column.export(export_buf, file_type="stl")
    stl_bytes = export_buf.getvalue()

    machine_profile = {
        "limits": {
            "nozzle_length": 3.0,
            "nozzle_holder_radius": 5.0,
            "ranges": {},
        }
    }

    result, diagnostics = GeometryApplicationService.execute(
        job_id="tall_col",
        file_bytes=stl_bytes,
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": 0.2, "bed_center_z": 0.0},
        machine_profile=machine_profile,
    )

    # The chunk path wraps a failed job result under "toolpath_job".
    job_result = result.get("toolpath_job", result)
    assert "error" in job_result, (
        "Expected the tall-column job to fail with a collision error; "
        f"got result={result!r}, "
        f"diagnostics={[str(d) for d in diagnostics]}"
    )
    assert "Collision" in str(job_result["error"])

    # The collision must come from a side face, not the bottom face (z=0).
    profile = SlicerMachineProfile(nozzle_length=3.0, nozzle_holder_radius=5.0)
    part_bvh = MeshBVH(vertices=column.vertices, faces=column.faces)
    engine = CollisionEngine(profile=profile, part_bvh=part_bvh, bed_center_z=0.0)

    # Holder end colliding with the column's side wall:
    # tip at (7, 0, 45), normal (0, 0, 1) -> holder_end = tip + nozzle_length * normal = (7, 0, 48).
    holder_end = np.array([7.0, 0.0, 48.0])
    closest_pt, dist = engine.query_closest_point(holder_end, current_z=50.0)

    assert closest_pt is not None, (
        "Expected a closest surface point from the column; got None"
    )
    assert closest_pt[2] > 1.0, (
        f"Expected collision from a side face (z > 1.0), "
        f"got closest point z={float(closest_pt[2]):.4f} (bottom face is at z=0)"
    )
    assert dist < 5.0, (
        f"Expected closest point within holder radius (dist < 5.0), "
        f"got dist={dist:.4f}"
    )
