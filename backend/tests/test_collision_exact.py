import os
import numpy as np
import trimesh
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from shapely.ops import triangulate as shapely_triangulate

from collision import CollisionEngine
from bvh import MeshBVH
from models import SlicerMachineProfile


# Maximum sample spacing (mm) for the independent reference surface samples.
_REFERENCE_SPACING_MM = 0.5

# Small tolerance applied when deciding whether a vertex sits at the clip plane.
_CLIP_TOLERANCE = 1e-6


def make_box(min_x, min_y, min_z, max_x, max_y, max_z):
    """Create a box mesh as (vertices, faces) arrays."""
    vertices = np.array([
        [min_x, min_y, min_z],
        [max_x, min_y, min_z],
        [max_x, max_y, min_z],
        [min_x, max_y, min_z],
        [min_x, min_y, max_z],
        [max_x, min_y, max_z],
        [max_x, max_y, max_z],
        [min_x, max_y, max_z],
    ], dtype=float)
    faces = np.array([
        [0, 1, 2], [0, 2, 3],  # bottom (z=min_z)
        [4, 7, 6], [4, 6, 5],  # top (z=max_z)
        [0, 4, 5], [0, 5, 1],  # front (y=min_y)
        [3, 2, 6], [3, 6, 7],  # back (y=max_y)
        [0, 3, 7], [0, 7, 4],  # left (x=min_x)
        [1, 5, 6], [1, 6, 2],  # right (x=max_x)
    ], dtype=int)
    return vertices, faces


def make_engine(vertices, faces, nozzle_length=40.0, nozzle_holder_radius=5.0,
                bed_center_z=0.0):
    """Build a CollisionEngine from a mesh."""
    profile = SlicerMachineProfile(
        nozzle_length=nozzle_length,
        nozzle_holder_radius=nozzle_holder_radius,
    )
    bvh = MeshBVH(vertices=vertices, faces=faces)
    return CollisionEngine(profile=profile, part_bvh=bvh, bed_center_z=bed_center_z)


def test_reference_pose_accepted():
    """Test (a): Reference pose accepted — empty printed BVH at current_z=1.4.

    Box from z=38.42 to z=100.  Tip at (50, 50, 1.4), vertical nozzle.
    holder_end = (50, 50, 41.4); distance to wall bottom (z=38.42) = 2.98 mm
    (< 5 mm radius, would collide with the old heuristic).  But nothing is
    printed at z <= 1.4, so the printed BVH is empty and validate_pose returns
    None.
    """
    # Box occupies z in [38.42, 100]; nothing printed at current_z = 1.4.
    vertices, faces = make_box(0, 0, 38.42, 100, 100, 100)
    engine = make_engine(vertices, faces)

    result = engine.validate_pose(50.0, 50.0, 1.4, 0.0, 0.0, 1.0, current_z=1.4)
    assert result is None


def test_tilted_nozzle_holder_inside_wall():
    """Test (b): Tilted nozzle — holder inside radius of printed wall → "part".

    Wall box at x in [-1, 1], z in [0, 50] (printed portion).
    nozzle_length = 3.0 (short enough for holder to reach the wall).
    Tip at (3.0, 0.0, 50.0), normal = (-0.9, 0, 0.436) tilted toward wall.
    holder_end ≈ (0.3, 0, 51.308); nearest printed material (z <= 50) on the
    wall's top face at (0.3, 0, 50.0) is 1.308 mm away (< 5 mm radius).
    """
    # Printed wall: x in [-1, 1], y in [-5, 5], z in [0, 50]
    vertices, faces = make_box(-1, -5, 0, 1, 5, 50)
    engine = make_engine(
        vertices, faces, nozzle_length=3.0, nozzle_holder_radius=5.0
    )

    result = engine.validate_pose(
        3.0, 0.0, 50.0, -0.9, 0.0, 0.436, current_z=50.0
    )
    assert result == "part"


# ---------------------------------------------------------------------------
# Independent reference (does NOT import collision.py)
# ---------------------------------------------------------------------------

def _clip_with_cap(vertices, faces, z_plane, cache):
    """Clip a mesh at z=z_plane (keep below) and add a cap, independent of collision.py.

    Mirrors CollisionEngine._clip_mesh_at_z:
      * trimesh.slice_plane keeps the portion at/below z_plane, cutting
        triangles that straddle the plane.
      * Boundary edges at z_plane are polygonized (shapely) and triangulated
        to form a cap.

    Results are cached by z_plane rounded to 0.1 mm.
    """
    key = round(float(z_plane), 1)
    if key in cache:
        return cache[key]

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    below = mesh.slice_plane(
        plane_origin=[0.0, 0.0, z_plane],
        plane_normal=[0.0, 0.0, -1.0],
    )
    if below is None or len(below.faces) == 0:
        cache[key] = None
        return None

    v = np.asarray(below.vertices, dtype=float)
    f = np.asarray(below.faces, dtype=int)

    # Count face adjacency per unique edge to find boundary edges.
    edge_face_count = {}
    for face in f:
        for i in range(3):
            e0, e1 = int(face[i]), int(face[(i + 1) % 3])
            ek = (min(e0, e1), max(e0, e1))
            edge_face_count[ek] = edge_face_count.get(ek, 0) + 1

    # Boundary edges at z_plane: one adjacent face, both vertices on the plane.
    boundary_edges = []
    for (e0, e1), count in edge_face_count.items():
        if count != 1:
            continue
        if not (
            np.isclose(v[e0, 2], z_plane, atol=_CLIP_TOLERANCE)
            and np.isclose(v[e1, 2], z_plane, atol=_CLIP_TOLERANCE)
        ):
            continue
        boundary_edges.append((e0, e1))

    v_new = v.copy()
    f_new = f.copy()

    if boundary_edges:
        lines = [LineString([v[e0][:2], v[e1][:2]]) for e0, e1 in boundary_edges]
        merged = unary_union(lines)
        cap_polys = list(polygonize(merged))

        new_verts = []
        new_faces = []

        for poly in cap_polys:
            if poly.area < 1e-12:
                continue
            tris = shapely_triangulate(poly)
            for tri in tris:
                coords = np.array(tri.exterior.coords[:-1])  # (3, 2)
                tri_indices = []
                for coord in coords:
                    match = np.where(
                        np.isclose(v_new[:, 0], coord[0], atol=_CLIP_TOLERANCE)
                        & np.isclose(v_new[:, 1], coord[1], atol=_CLIP_TOLERANCE)
                        & np.isclose(v_new[:, 2], z_plane, atol=_CLIP_TOLERANCE)
                    )[0]
                    if len(match) > 0:
                        tri_indices.append(int(match[0]))
                    else:
                        new_idx = len(v_new) + len(new_verts)
                        new_verts.append(
                            [float(coord[0]), float(coord[1]), float(z_plane)]
                        )
                        tri_indices.append(new_idx)
                if len(tri_indices) == 3:
                    new_faces.append(tri_indices)

        if new_verts:
            v_new = np.vstack([v_new, np.array(new_verts, dtype=float)])
        if new_faces:
            f_new = np.vstack([f_new, np.array(new_faces, dtype=int)])

    cache[key] = (v_new, f_new)
    return (v_new, f_new)


def reference_part_collision(vertices, faces, holder_end, holder_radius,
                             current_z, cache):
    """Independent part-collision reference that does NOT import collision.py.

    Prints material = mesh clipped at z=current_z with a cap.  The surface is
    dense-sampled at <= 0.5 mm spacing.  Collision when the holder end is
    within holder_radius of any sample.
    """
    clipped = _clip_with_cap(vertices, faces, current_z, cache)
    if clipped is None:
        return None

    v, f = clipped
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=False)

    # <= 0.5 mm spacing  ->  >= 1 / 0.5^2 samples per square mm.
    count = max(8, int(np.ceil(float(mesh.area) / (_REFERENCE_SPACING_MM ** 2))))
    samples, _ = trimesh.sample.sample_surface(mesh, count)

    min_dist = float(np.linalg.norm(samples - holder_end, axis=1).min())
    if min_dist < holder_radius:
        return "part"
    return None


def test_random_poses_agree_with_independent_reference():
    """Test (c): >= 200 random poses per mesh agree with an independent reference.

    The reference clips the mesh at current_z (trimesh.slice_plane), builds the
    cap from boundary edges (shapely polygonize + triangulate), dense-samples
    the surface at <= 0.5 mm spacing (trimesh.sample.sample_surface), and
    declares collision when the holder end is within holder_radius of a sample.

    Because every sample lies on the real printed surface, the reference can
    never hallucinate a collision: zero false negatives
    (validate_pose=None but reference=collision) is required.

    The reference can miss narrow features between samples, so false positives
    (validate_pose=collision but reference=None) are possible; they are printed
    and asserted < 5%.
    """
    np.random.seed(42)
    nozzle_length = 40.0
    holder_radius = 5.0
    profile = SlicerMachineProfile(
        nozzle_length=nozzle_length,
        nozzle_holder_radius=holder_radius,
    )
    n_poses = 200

    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    pipe_mesh = trimesh.load(os.path.join(fixtures_dir, "pipe_fitting.stl"))
    pipe_v = np.asarray(pipe_mesh.vertices, dtype=float)
    pipe_f = np.asarray(pipe_mesh.faces, dtype=int)

    coarse_v, coarse_f = make_box(-5.0, -5.0, 0.0, 5.0, 5.0, 100.0)

    # Bed is placed far below (bed_center_z=1000 -> bed_z=-1000) so the test
    # isolates part collision and never sees a "bed" result.
    meshes = [
        ("pipe_fitting.stl", pipe_v, pipe_f, pipe_mesh.bounds),
        ("coarse_10x10x100_box", coarse_v, coarse_f, None),
    ]

    total_poses = 0
    total_fn = 0
    total_fp = 0

    for name, vertices, faces, bounds in meshes:
        bvh = MeshBVH(vertices=vertices, faces=faces)
        engine = CollisionEngine(
            profile=profile, part_bvh=bvh, bed_center_z=1000.0
        )
        cache = {}

        fn = 0
        fp = 0

        for _ in range(n_poses):
            if bounds is not None:
                lo = bounds[0]
                hi = bounds[1]
                x = float(np.random.uniform(lo[0], hi[0]))
                y = float(np.random.uniform(lo[1], hi[1]))
                z = float(np.random.uniform(lo[2], hi[2]))
            else:
                x = float(np.random.uniform(-10.0, 10.0))
                y = float(np.random.uniform(-10.0, 10.0))
                z = float(np.random.uniform(0.0, 100.0))

            # Random unit normal vector.
            theta = float(np.random.uniform(0.0, np.pi))
            phi = float(np.random.uniform(0.0, 2.0 * np.pi))
            nx = float(np.sin(theta) * np.cos(phi))
            ny = float(np.sin(theta) * np.sin(phi))
            nz = float(np.cos(theta))

            current_z = float(np.random.uniform(0.0, 100.0))

            holder_end = np.array([x, y, z], dtype=float) + \
                np.array([nx, ny, nz], dtype=float) * nozzle_length

            result = engine.validate_pose(
                x, y, z, nx, ny, nz, current_z=current_z
            )
            expected = reference_part_collision(
                vertices, faces, holder_end, holder_radius, current_z, cache
            )

            engine_collide = result is not None
            ref_collide = expected is not None

            if ref_collide and not engine_collide:
                fn += 1  # false negative: engine missed a real collision
            elif engine_collide and not ref_collide:
                fp += 1  # false positive: engine collided, reference did not

        fp_rate = fp / n_poses
        print(
            f"\n[{name}] poses={n_poses} "
            f"false_negatives={fn} false_positives={fp} "
            f"false_positive_rate={fp_rate:.3f}"
        )
        total_poses += n_poses
        total_fn += fn
        total_fp += fp

        assert fn == 0, f"{name}: {fn} false negatives"
        assert fp_rate < 0.05, (
            f"{name}: false-positive rate {fp_rate:.3f} >= 5%"
        )

    overall_fp_rate = total_fp / total_poses
    print(
        f"\n[TOTAL] poses={total_poses} "
        f"false_negatives={total_fn} false_positives={total_fp} "
        f"false_positive_rate={overall_fp_rate:.3f}"
    )
    assert total_fn == 0, f"{total_fn} total false negatives"
    assert overall_fp_rate < 0.05, (
        f"overall false-positive rate {overall_fp_rate:.3f} >= 5%"
    )


def test_box_side_face_collision():
    """Box 10x10x100 (z in [0, 100]); holder within radius of a SIDE face.

    current_z=50 so material up to z=50 is printed.  nozzle_length=3.0,
    holder_radius=5.0.

    Vertical:  tip=(7, 0, 45), normal=(0, 0, 1)  ->  holder_end=(7, 0, 48).
    Distance to the side wall at x=5 is 2.0 mm < 5 mm -> "part".

    Tilted:    tip=(7, 0, 45), normal=(-0.9, 0, 0.436)
    ->  holder_end≈(4.3, 0, 46.3), still beside the side wall -> "part".
    """
    vertices, faces = make_box(-5.0, -5.0, 0.0, 5.0, 5.0, 100.0)
    engine = make_engine(
        vertices, faces, nozzle_length=3.0, nozzle_holder_radius=5.0
    )

    # Vertical nozzle: holder_end=(7, 0, 48), 2.0 mm from side wall at x=5.
    result = engine.validate_pose(7.0, 0.0, 45.0, 0.0, 0.0, 1.0, current_z=50.0)
    assert result == "part"

    # Tilted nozzle toward the side wall: holder_end≈(4.3, 0, 46.3).
    result = engine.validate_pose(
        7.0, 0.0, 45.0, -0.9, 0.0, 0.436, current_z=50.0
    )
    assert result == "part"


def test_side_face_not_bottom_face():
    """Box 10x10x100, current_z=50: collision must come from a side face,
    not the bottom face at z=0."""
    vertices, faces = make_box(-5.0, -5.0, 0.0, 5.0, 5.0, 100.0)
    engine = make_engine(
        vertices, faces, nozzle_length=3.0, nozzle_holder_radius=5.0
    )

    x, y, z = 7.0, 0.0, 45.0
    nx, ny, nz = 0.0, 0.0, 1.0
    current_z = 50.0

    result = engine.validate_pose(x, y, z, nx, ny, nz, current_z=current_z)
    assert result == "part"

    tip = np.array([x, y, z], dtype=float)
    normal = np.array([nx, ny, nz], dtype=float)
    holder_end = tip + normal * engine.profile.nozzle_length

    closest_point, distance = engine.query_closest_point(
        holder_end, current_z=current_z
    )
    assert closest_point is not None
    assert distance < engine.profile.nozzle_holder_radius
    # Closest surface point must be on the side wall (z well above 0),
    # not the bottom face at z=0.
    assert closest_point[2] > 1.0, (
        f"closest point {closest_point} is on the bottom face"
    )
