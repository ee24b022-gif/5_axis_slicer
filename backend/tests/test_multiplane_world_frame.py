"""
Multi-plane world-frame regression & acceptance battery.

Purpose
=======
These tests pin the intended, post-fix semantics of multi-directional
(indexed multi-plane) 5-axis slicing against pipe_fitting.stl:

* World-frame toolpath: sliced paths are expressed in WORLD coordinates,
  with per-point normals derived from the chunk's slice plane (never
  hard-coded (0,0,1)), so the rotary axes get real tilt angles (U=30 for
  the tilted plane below).
* Printing order: chunk list order == printing order.
  - chunk_builder.build_capped_chunks (chunk_builder.py:18-37) appends
    mesh.copy() as chunk 0, then the positive-normal side of EACH
    configured slice plane in configuration order.
  - chunk_builder.subtract_later_chunks (chunk_builder.py:43-60)
    subtracts every later chunk from every earlier chunk, so the list
    order 0..N is the print order: chunk 0 (below plane 1) prints
    first, then chunk 1, then chunk 2 (above the tilted plane 2).
* Chunk metadata partition: chunk layer ranges must tile
    [0 .. len(layers_data)-1] consecutively with no gaps/overlaps
    (test_g/test_i). NOTE: current code only fixes layer_idx_max on the
    last chunk (geometry_service.py:478); earlier chunks keep the stale
    seed value equal to their layer_idx_min.
* G-code shell geometry (test_h): for the three-axis chunk the emitted
  perimeter must follow the original section polygon boundary (within
  0.01 mm), i.e. the toolpath is defined by the world-frame section
  geometry ("world-defines"), not decimated by the 2.5 mm collision
  resampling or inset by the 0.2 mm shell buffer.
* Diagnostics discipline (test_k): a failed preflight or a legacy
  slicer error must never be accompanied by a passing "S-001 Slicing
  completed." diagnostic.

Half-layer offset note
======================
generate_layer_schedule defaults half_layer_offset=True: the first
slice of every chunk sits at z_min + layer_height/2 (then
z_min + layer_height + layer_height/2 + i*layer_height). For the tilted
chunk (chunk 2) whose local z is the signed distance to plane 2, the
first layer therefore lies at plane offset == layer_height/2 == 0.1 mm
(NOT 0). test_d asserts that exact lattice, not dot==0.

G-code (.3f) quantization note (test_d tolerance)
=================================================
The recover-lattice assertion uses an absolute 1e-3 mm tolerance on
dot(world_point - plane_origin, unit_normal) rather than the spec's
1e-3 on the dimensionless layer index k = (dot - h/2)/h. Reason: the
emitted machine coordinates are rounded to 0.001 mm (":.3f"), which
injects up to 8.66e-4 mm into the recovered dot (worst-case coherent
rounding of X/Y/Z along a unit direction; measured systematic residual
-2.5e-4 on a probe). k-index tolerance of 1e-3 would demand 2e-4 mm
(h=0.2), below the physical quantization floor. The dot tolerance of
1e-3 mm is the tightest sound bound and still detects any real
frame/normal error (those produce millimetre-scale deviations).
"""

import io
import math
import os
import re
import time
import uuid

import numpy as np
import pytest
import trimesh

from fastapi.testclient import TestClient

from main import app
from database import engine, Base, SessionLocal
from models import User, MachineProfile, Chunk, Layer, SlicerMachineProfile
from dependencies import get_current_actor, Actor
from enums import UserRole, JobMode, DiagnosticStatus, DiagnosticSeverity

import geometry_service
import transform_utils
from geometry_service import GeometryApplicationService
from layer_schedule import generate_layer_schedule
from slice_intersection import slice_mesh_at_z
from polygonization import reconstruct_polygons
from collision import CollisionEngine
from bvh import MeshBVH
from slice_plane_model import SlicePlane
from transform_utils import align_chunk_to_slice_plane

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PIPE_STL = os.path.join(FIXTURE_DIR, "pipe_fitting.stl")

LAYER_HEIGHT = 0.2
BED_CENTER_Z = 0.0
NOZZLE_LENGTH = 40.0
NOZZLE_HOLDER_RADIUS = 5.0

# G-code lattice tolerance justification lives in the module docstring.
LATTICE_DOT_TOL = 1.0e-3


# ---------------------------------------------------------------------------
# Slice planes (module constants).
#
# The pipe spans x in [-54.5, 54.5], y in [-33.3, 33.3], z in [0, 133.75]
# after the canonical transform.
# PLANE1 slightly tilted near-horizontal plane at z=50: chunk 0 == pipe
# below plane 1, chunk 1 == pipe above plane 1 (minus chunk 2 region).
# A purely horizontal plane cannot be used: plane_preflight rejects
# theta==0 normals (INVALID_PLANE_THETA_ZERO), so plane 1 is tilted 5 deg.
# PLANE2 tilted 30 deg from vertical through (0,0,50): chunk 2 == pipe
# above plane 2. For n2=(0.5,0,sqrt(3)/2) the UV adapter yields
# U = degrees(atan2(hypot(nx,ny), nz)) = 30.000 and
# V = degrees(atan2(nx, ny)) = 90.000 EXACTLY.
# local_x/local_y frames: orthonormal, right-handed (local_y = cross(n, x)).
# ---------------------------------------------------------------------------
_S3 = math.sqrt(3.0) / 2.0
_SIN5 = math.sin(math.radians(5.0))
_COS5 = math.cos(math.radians(5.0))

PLANE1 = {
    "plane_origin": (0.0, 0.0, 50.0),
    "unit_normal": (0.0, _SIN5, _COS5),
    "angle_pair": (5.0, 0.0),
    "angle_units": "degrees",
    "rotation_convention": "AC_TABLE",
    "local_x": (1.0, 0.0, 0.0),
    "local_y": (0.0, _COS5, -_SIN5),
    "source_frame": "canonical",
}

PLANE2 = {
    "plane_origin": (0.0, 0.0, 50.0),
    "unit_normal": (0.5, 0.0, _S3),
    "angle_pair": (30.0, 90.0),
    "angle_units": "degrees",
    "rotation_convention": "AC_TABLE",
    "local_x": (0.0, 1.0, 0.0),
    "local_y": (-_S3, 0.0, 0.5),
    "source_frame": "canonical",
}

PLANE_NO_HIT = {
    "plane_origin": (0.0, 0.0, 100000.0),
    "unit_normal": (0.0, 0.0, 1.0),
    "angle_pair": (0.0, 0.0),
    "angle_units": "degrees",
    "rotation_convention": "AC_TABLE",
    "local_x": (1.0, 0.0, 0.0),
    "local_y": (0.0, 1.0, 0.0),
    "source_frame": "canonical",
}
# NOTE: with normal (0,0,1) the preflight theta-zero guard fires
# (INVALID_PLANE_THETA_ZERO FAIL, blocking) which is the outcome test_k
# needs: a blocking preflight failure. A slightly tilted far-away plane
# would reach NONINTERSECTING_PLANE instead; both block execution.

BED_LIMITS = {"X": (-200.0, 200.0), "Y": (-200.0, 200.0), "Z": (0.0, 300.0)}
ROTARY_LIMITS = {"U": (-360.0, 360.0), "V": (-360.0, 360.0)}
FULL_LIMITS = {**BED_LIMITS, **ROTARY_LIMITS}

MACHINE_PROFILE_DIRECT = {
    "limits": {
        "nozzle_length": NOZZLE_LENGTH,
        "nozzle_holder_radius": NOZZLE_HOLDER_RADIUS,
        "ranges": BED_LIMITS,
    }
}


# ---------------------------------------------------------------------------
# Shared helpers (pure functions).
# ---------------------------------------------------------------------------

def _aligned_pipe_mesh() -> trimesh.Trimesh:
    """Load pipe_fitting.stl and apply the production canonical transform."""
    mesh = trimesh.load(PIPE_STL)
    assert mesh.is_watertight, "pipe_fitting.stl must be watertight"
    aligned, _canon_matrix = transform_utils.apply_canonical_transform(mesh.copy())
    return aligned


def _pipe_stl_bytes() -> bytes:
    """Canonical-aligned pipe mesh serialized as in-memory STL."""
    aligned = _aligned_pipe_mesh()
    out = io.BytesIO()
    aligned.export(out, file_type="stl")
    return out.getvalue()


def _stl_bytes_of(mesh: trimesh.Trimesh) -> bytes:
    out = io.BytesIO()
    mesh.export(out, file_type="stl")
    return out.getvalue()


_MOVE_RE = re.compile(r"^G[01]\s+X(-?\d*\.?\d+)\s+Y(-?\d*\.?\d+)\s+Z(-?\d*\.?\d+)")
_U_RE = re.compile(r"\bU(-?\d*\.?\d+)\b")
_V_RE = re.compile(r"\bV(-?\d*\.?\d+)\b")


def _parse_gcode_moves(gcode_text: str):
    """Parse G0/G1 motion lines that carry X/Y/Z machine coordinates.

    Retraction lines (``G1 E... F...``) carry no X and are skipped.
    Returns a list of dicts with machine coords (x,y,z), rotary angles
    (u,v in degrees or None), and is_travel (":  ; Travel" marker).
    """
    moves = []
    for raw_line in gcode_text.split("\n"):
        match = _MOVE_RE.match(raw_line)
        if match is None:
            continue
        u_match = _U_RE.search(raw_line)
        v_match = _V_RE.search(raw_line)
        moves.append({
            "x": float(match.group(1)),
            "y": float(match.group(2)),
            "z": float(match.group(3)),
            "u": float(u_match.group(1)) if u_match else None,
            "v": float(v_match.group(1)) if v_match else None,
            "is_travel": "; Travel" in raw_line,
            "raw": raw_line,
        })
    return moves


def _rz_rotation(v_deg: float) -> np.ndarray:
    angle = math.radians(v_deg)
    cos_v, sin_v = math.cos(angle), math.sin(angle)
    return np.array([
        [cos_v, -sin_v, 0.0],
        [sin_v, cos_v, 0.0],
        [0.0, 0.0, 1.0],
    ])


def _rx_rotation(u_deg: float) -> np.ndarray:
    angle = math.radians(u_deg)
    cos_u, sin_u = math.cos(angle), math.sin(angle)
    return np.array([
        [1.0, 0.0, 0.0],
        [0.0, cos_u, -sin_u],
        [0.0, sin_u, cos_u],
    ])


def _recover_world_point(move: dict, bed_center_z: float) -> np.ndarray:
    """Invert TableTableUVAdapter.calculate_ik for one parsed G-code move.

    Forward (uv_adapter.py:12-55): p = [x, y, z + bed_center_z];
    R_total = R_u(u_rad) @ R_v(v_rad); rotated = R_total @ p;
    machine = [rotated[0], rotated[1], rotated[2] - bed_center_z].
    Inverse: p_rot = [mx, my, mz + bed_center_z]; p = R_total^T @ p_rot.
    """
    u_deg, v_deg = move["u"], move["v"]
    assert u_deg is not None and v_deg is not None, (
        f"Recovery requires parsed U/V angles; got {move!r}")
    r_total = _rx_rotation(u_deg) @ _rz_rotation(v_deg)
    p_rot = np.array([move["x"], move["y"], move["z"] + bed_center_z])
    part = r_total.T @ p_rot
    part[2] -= bed_center_z
    return part


def _uv_rotation_matrix(u_deg: float, v_deg: float) -> np.ndarray:
    """Same composition order as TableTableUVAdapter.calculate_ik."""
    return _rx_rotation(u_deg) @ _rz_rotation(v_deg)


def _chunk_ranges(chunks_data) -> list:
    """Ordered [chunk_idx, layer_idx_min, layer_idx_max] triples."""
    return sorted(
        (int(c["chunk_idx"]), int(c["layer_idx_min"]), int(c["layer_idx_max"]))
        for c in chunks_data
    )


# ---------------------------------------------------------------------------
# DB + auth scaffolding (mirrors tests/test_e2e_pipe_fitting.py).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()


@pytest.fixture(scope="module")
def default_user():
    db = SessionLocal()
    user = db.query(User).filter_by(username="multiplane_world_frame").first()
    if not user:
        user = User(
            username="multiplane_world_frame",
            email="multiplane_world_frame@example.com",
            hashed_password="pw",
            is_active=True,
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    data = user
    db.close()
    return data


@pytest.fixture(scope="module", autouse=True)
def override_auth(default_user):
    actor = Actor(
        actor_type="USER",
        user_id=default_user.id,
        key_id=None,
        scopes=["*"],
        user=default_user,
    )
    previous_override = app.dependency_overrides.get(get_current_actor)
    app.dependency_overrides[get_current_actor] = lambda: actor
    yield
    # Restore whatever the session-scoped conftest override had installed
    # so other test modules in the same pytest run are unaffected.
    if previous_override is not None:
        app.dependency_overrides[get_current_actor] = previous_override
    else:
        app.dependency_overrides.pop(get_current_actor, None)


@pytest.fixture(scope="module")
def machine_profile_id(default_user):
    db = SessionLocal()
    profile = MachineProfile(
        name="Multiplane World Frame Machine",
        revision=1,
        dialect="marlin",
        author_id=default_user.id,
        contract={
            "calibration_revision": 1,
            "kinematic_convention": "AC_TABLE",
            "units": "mm",
            "axis_names": ["X", "Y", "Z", "U", "V"],
            "axis_directions": {"X": 1, "Y": 1, "Z": 1, "U": 1, "V": 1},
            "zero_positions": {"X": 0.0, "Y": 0.0, "Z": 0.0, "U": 0.0, "V": 0.0},
            "command_templates": {"linear_move": "G1"},
        },
        limits={
            "ranges": FULL_LIMITS,
            "nozzle_length": NOZZLE_LENGTH,
            "nozzle_holder_radius": NOZZLE_HOLDER_RADIUS,
        },
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    pid = str(profile.id)
    db.close()
    return pid


# ---------------------------------------------------------------------------
# Job fixtures (module scope — run once, reused by many assertions).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def two_plane_api(machine_profile_id):
    """Upload pipe_fitting.stl and submit an indexed_multidirectional job
    with slice_planes [PLANE1, PLANE2] through the HTTP API; then query
    status/preview/export and read Chunk/Layer rows straight from the DB.

    Returns a dict; tests do the asserting.
    """
    with TestClient(app) as client:
        with open(PIPE_STL, "rb") as f:
            upload_resp = client.post(
                "/meshes",
                files={"file": ("pipe_fitting.stl", f, "application/octet-stream")},
            )
        assert upload_resp.status_code == 200, upload_resp.text
        mesh_id = upload_resp.json()["id"]

        job_resp = client.post(
            "/jobs",
            json={
                "mesh_id": mesh_id,
                "machine_profile_id": machine_profile_id,
                "mode": "indexed_multidirectional",
                "settings": {
                    "layer_height": LAYER_HEIGHT,
                    "bed_center_z": BED_CENTER_Z,
                    "slice_planes": [dict(PLANE1), dict(PLANE2)],
                },
            },
        )
        assert job_resp.status_code == 201, job_resp.text
        job_id = job_resp.json()["id"]
        # Returning inside the `with` block ends the context, which lets
        # the background task run to completion before we query results.
        return _collect_two_plane_api_results(job_id)


def _collect_two_plane_api_results(job_id):
    """Second client session + DB reads after the background job finished."""
    with TestClient(app) as client:
        status_resp = client.get(f"/jobs/{job_id}")
        assert status_resp.status_code == 200, status_resp.text
        status_payload = status_resp.json()

        preview_resp = client.get(f"/jobs/{job_id}/preview")
        assert preview_resp.status_code == 200, preview_resp.text
        preview_payload = preview_resp.json()

        export_resp = client.get(f"/jobs/{job_id}/export")
        export_status = export_resp.status_code
        export_bytes = export_resp.content if export_status == 200 else b""

    db = SessionLocal()
    try:
        job_uuid = uuid.UUID(str(job_id))
        chunk_rows = db.query(Chunk).filter(Chunk.job_id == job_uuid).all()
        chunk_db_rows = [
            {
                "chunk_idx": int(c.chunk_idx),
                "layer_idx_min": int(c.layer_idx_min),
                "layer_idx_max": int(c.layer_idx_max),
                "min_z": float(c.min_z),
                "max_z": float(c.max_z),
                "validity": str(c.validity.value)
                if hasattr(c.validity, "value") else str(c.validity),
            }
            for c in chunk_rows
        ]
        layer_rows = (
            db.query(Layer)
            .filter(Layer.job_id == job_uuid)
            .order_by(Layer.layer_idx.asc())
            .all()
        )
        layer_db_rows = [
            {
                "layer_idx": int(l.layer_idx),
                "z_height": float(l.z_height),
                "thickness": float(l.thickness),
                "is_support": bool(l.is_support),
            }
            for l in layer_rows
        ]
    finally:
        db.close()

    return {
        "job_id": str(job_id),
        "status_payload": status_payload,
        "preview_payload": preview_payload,
        "export_status": export_status,
        "export_bytes": export_bytes,
        "chunk_db_rows": chunk_db_rows,
        "layer_db_rows": layer_db_rows,
    }


@pytest.fixture(scope="module")
def two_plane_direct():
    """Direct GeometryApplicationService._execute_chunk_path call with
    slice_planes [PLANE1, PLANE2] at layer height 0.2 (bed_center_z 0.0).

    Returns (result, diagnostics, layers_data, chunks_data) plus the
    aligned mesh used for the run.
    """
    aligned = _aligned_pipe_mesh()
    result, diagnostics, layers_data, chunks_data = (
        GeometryApplicationService._execute_chunk_path(
            job_id="dp",
            aligned_mesh=aligned,
            job_mode=JobMode.INDEXED_MULTIDIRECTIONAL,
            job_settings={
                "layer_height": LAYER_HEIGHT,
                "bed_center_z": BED_CENTER_Z,
                "slice_planes": [dict(PLANE1), dict(PLANE2)],
            },
            machine_profile=MACHINE_PROFILE_DIRECT,
            layer_height=LAYER_HEIGHT,
            bed_center_z=BED_CENTER_Z,
        )
    )
    return {
        "job_id": "dp",
        "result": result,
        "diagnostics": diagnostics,
        "layers_data": layers_data,
        "chunks_data": chunks_data,
        "aligned_mesh": aligned,
    }


@pytest.fixture(scope="module")
def single_plane_threeaxis_direct():
    """Direct execute() run: whole pipe through the three-axis path
    (no slice_planes -> single chunk). Reused by tests g/h.
    """
    file_bytes = _pipe_stl_bytes()
    result, diagnostics = GeometryApplicationService.execute(
        job_id="threeaxis-direct",
        file_bytes=file_bytes,
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": LAYER_HEIGHT, "bed_center_z": BED_CENTER_Z},
        machine_profile=MACHINE_PROFILE_DIRECT,
    )
    return {"result": result, "diagnostics": diagnostics}


# ---------------------------------------------------------------------------
# (a) API completeness: chunks persisted, layers bound to ranges, export.
# ---------------------------------------------------------------------------

def test_a_two_plane_api_complete_with_chunks_layers_export(two_plane_api):
    payload = two_plane_api
    status = payload["status_payload"]
    assert status["status"] == "complete", (
        f"Expected indexed_multidirectional job to be 'complete', got "
        f"{status['status']!r}; mode={status.get('mode')!r}"
    )

    layers = payload["preview_payload"]["layers"]
    assert len(layers) > 0, (
        f"Expected preview layers > 0 for job {payload['job_id']}, got "
        f"{len(layers)} (job status {status['status']!r})"
    )

    assert payload["export_status"] == 200, (
        f"Expected export HTTP 200 for completed job, got "
        f"{payload['export_status']}"
    )

    # DB chunk rows: exactly chunks 0, 1, 2, all valid, ordered.
    chunk_rows = payload["chunk_db_rows"]
    chunk_indices = {row["chunk_idx"] for row in chunk_rows}
    assert chunk_indices == {0, 1, 2}, (
        f"Expected DB Chunk rows for chunk_idx exactly {{0, 1, 2}}, got "
        f"{sorted(chunk_indices)} (rows: {chunk_rows}). A missing chunk "
        f"means slice-plane chunking or persistence dropped a chunk."
    )
    invalid = [row for row in chunk_rows if row["validity"] != "valid"]
    assert not invalid, f"All three chunks must be 'valid', got invalid rows: {invalid}"

    rows_by_idx = {row["chunk_idx"]: row for row in chunk_rows}
    assert [idx for idx in sorted(rows_by_idx)] == [0, 1, 2]

    # Every persisted Layer row must belong to the union of the chunk
    # layer ranges (chunks own their global layer window).
    layer_indices = [row["layer_idx"] for row in payload["layer_db_rows"]]
    assert layer_indices, (
        f"Expected persisted Layer rows for job {payload['job_id']}, got none"
    )
    union = set()
    for chunk_idx in (0, 1, 2):
        row = rows_by_idx[chunk_idx]
        union.update(range(row["layer_idx_min"], row["layer_idx_max"] + 1))
    outside = sorted(set(layer_indices) - union)
    assert not outside, (
        f"{len(outside)} persisted layer indices fall outside the union of "
        f"chunk layer ranges; first offenders={outside[:10]}; "
        f"chunk rows={chunk_rows}; layer idx range="
        f"[{min(layer_indices)}, {max(layer_indices)}]. Chunk metadata "
        f"(layer_idx_min/max) must cover every printed layer."
    )


# ---------------------------------------------------------------------------
# (b) Tilted chunk emits rotary moves; machine coords inside bed limits.
# ---------------------------------------------------------------------------

def test_b_tilted_chunk_uv_and_bounds(two_plane_api):
    export_bytes = two_plane_api["export_bytes"]
    assert export_bytes, (
        f"Expected non-empty export bytes (status "
        f"{two_plane_api['export_status']})"
    )
    lines = export_bytes.decode("utf-8", errors="replace").split("\n")
    moves = _parse_gcode_moves("\n".join(lines))
    assert moves, "Export G-code contains no parsed G0/G1 motion lines"

    u_values = [m["u"] for m in moves if m["u"] is not None]
    assert u_values, (
        "No parsed move carries U angles; rotary axes were not emitted."
    )
    assert not all(abs(u) <= 1e-9 for u in u_values), (
        f"All {len(u_values)} parsed U angles are zero: tilt normals are "
        f"hard-coded (0,0,1) instead of world-frame plane normals. "
        f"Sample lines: {[m['raw'] for m in moves[:5]]}"
    )

    tilted = [
        m for m in moves
        if m["u"] is not None and m["v"] is not None
        and abs(m["u"] - 30.0) <= 0.1 and abs(m["v"] - 90.0) <= 0.1
    ]
    assert tilted, (
        "No G-code move carries U~30.000, V~90.000: the chunk above the "
        f"30-degree tilted plane 2 was not emitted with rotary angles "
        f"(parsed U values seen: {sorted(set(round(u, 3) for u in u_values))[:10]})."
    )

    offenders = []
    for move in moves:
        for axis, value in (("X", move["x"]), ("Y", move["y"]), ("Z", move["z"])):
            low, high = BED_LIMITS[axis]
            if not (low <= value <= high):
                offenders.append((move["raw"], axis, value))
    assert not offenders, (
        f"{len(offenders)} machine coordinates violate BED_LIMITS "
        f"{BED_LIMITS}; first offenders: {offenders[:5]}"
    )


# ---------------------------------------------------------------------------
# (c) Tilted chunk normals come from the plane, not hard-coded.
# ---------------------------------------------------------------------------

def test_c_tilted_not_hardcoded_normals(two_plane_direct):
    chunks_data = two_plane_direct["chunks_data"]
    by_idx = {int(c["chunk_idx"]): c for c in chunks_data}
    assert 2 in by_idx, (
        f"chunks_data has no chunk_idx==2 entry; present indices: "
        f"{sorted(by_idx)}. Chunk 2 (above tilted plane 2) must exist."
    )
    tilted_chunk = by_idx[2]

    payload = two_plane_direct["result"]
    gcode = payload.get("toolpath_job", payload).get("gcode_string", "")
    assert gcode, "result exposes an empty gcode_string"

    moves = _parse_gcode_moves(gcode)
    u_values = [m["u"] for m in moves if m["u"] is not None]
    near_30 = [u for u in u_values if abs(u - 30.0) <= 0.1]
    assert near_30, (
        "G-code contains no U~30 move: normals were hard-coded (0,0,1) or "
        f"U/V not emitted. Parsed distinct U values: "
        f"{sorted(set(round(u, 3) for u in u_values))[:12]}; chunk2 range="
        f"[{tilted_chunk['layer_idx_min']}, {tilted_chunk['layer_idx_max']}]"
    )

    tilted = [
        m for m in moves
        if m["u"] is not None and m["v"] is not None
        and abs(m["u"] - 30.0) <= 0.1 and abs(m["v"] - 90.0) <= 0.1
    ]
    assert tilted, (
        "No U~30 move also carries V~90. The tilted plane 2 normal "
        "(0.5, 0, sqrt(3)/2) maps to U=30.000, V=90.000 exactly through "
        "TableTableUVAdapter.calculate_ik; missing V pairing suggests "
        "angles are not derived from the world-frame normal."
    )


# ---------------------------------------------------------------------------
# (d) Tilted-chunk toolpath lies on the exact parallel-plane lattice.
#
# all_path_points are NOT exposed by the result payload (only path_count),
# so this test parses the produced G-code and inverts the machine IK to
# recover world-frame part coordinates. For n2=(0.5,0,sqrt(3)/2) the
# parsed U/V are exactly 30/90 degrees so the recovery is exact.
#
# The half-layer offset puts the first tilted-chunk slice at plane offset
# layer_height/2 == 0.1 mm; every later slice sits h further along, so
# every recovered dot((part - origin2), n2) must equal h/2 + k*h
# (k integer). Tolerance rationale in the module docstring.
# ---------------------------------------------------------------------------

def test_d_tilted_first_layer_on_plane_lattice(two_plane_direct):
    h = LAYER_HEIGHT
    result = two_plane_direct["result"]
    payload = result.get("toolpath_job", result)
    gcode = payload["gcode_string"]
    assert gcode, "result has empty gcode_string"

    moves = _parse_gcode_moves(gcode)
    tilt_moves = [
        m for m in moves
        if m["u"] is not None and m["v"] is not None
        and abs(m["u"] - 30.0) <= 0.1 and abs(m["v"] - 90.0) <= 0.1
    ]
    assert tilt_moves, (
        "No U~30/V~90 moves: tilted chunk toolpath not present in G-code, "
        "lattice cannot be verified."
    )

    n2 = np.array(PLANE2["unit_normal"], dtype=float)
    o2 = np.array(PLANE2["plane_origin"], dtype=float)

    dots = np.array([
        float((_recover_world_point(m, BED_CENTER_Z) - o2) @ n2)
        for m in tilt_moves
    ])

    k_indices = (dots - h / 2.0) / h
    resid_abs = np.abs(k_indices - np.round(k_indices)) * h
    worst = float(resid_abs.max())
    assert worst <= LATTICE_DOT_TOL, (
        f"Tilted-chunk recovered part points do not lie on the "
        f"plane-offset lattice h/2 + k*h (h={h}): worst deviation "
        f"{worst:.6f} mm > {LATTICE_DOT_TOL} mm, over {len(dots)} tilt "
        f"moves. dot range [{dots.min():.3f}, {dots.max():.3f}]. Points "
        f"off-lattice mean the world-frame z of the toolpath is not the "
        f"chunk-local schedule z."
    )

    first_dot = float(dots[0])
    assert abs(first_dot - h / 2.0) <= LATTICE_DOT_TOL, (
        f"First tilted-chunk G-code point sits at plane offset "
        f"{first_dot:.6f} mm, expected the half-layer-offset first slice "
        f"{h / 2.0:.6f} mm (within {LATTICE_DOT_TOL})."
    )


# ---------------------------------------------------------------------------
# (e) Collision clip caps match the true mesh cross-section area.
# ---------------------------------------------------------------------------

def test_e_cap_area_matches_section():
    mesh = trimesh.load(PIPE_STL)
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    engine = CollisionEngine(
        SlicerMachineProfile(nozzle_length=NOZZLE_LENGTH,
                             nozzle_holder_radius=NOZZLE_HOLDER_RADIUS),
        MeshBVH(vertices, faces),
        bed_center_z=BED_CENTER_Z,
    )

    for z in (1.0, 10.0, 40.0, 80.0):
        clip = engine._clip_mesh_at_z(vertices, faces, z)
        assert clip is not None, (
            f"_clip_mesh_at_z returned None at z={z}: the engine cannot "
            f"clip the pipe mesh at this height."
        )
        clipped_v, clipped_f = clip

        cap_mask = (
            np.abs(clipped_v[clipped_f][:, :, 2] - z) <= 1e-4
        ).all(axis=1)
        assert bool(np.any(cap_mask)), (
            f"Clip at z={z} produced no cap faces (faces whose 3 vertices "
            f"sit at |vz - {z}| <= 1e-4): the lower-material clip is "
            f"uncapped, so printed-BVH collision checks silently model an "
            f"open shell."
        )

        cap_triangles = clipped_v[clipped_f[cap_mask]]
        cap_normals = np.cross(
            cap_triangles[:, 1] - cap_triangles[:, 0],
            cap_triangles[:, 2] - cap_triangles[:, 0],
        )
        cap_area = float(0.5 * np.linalg.norm(cap_normals, axis=1).sum())
        assert cap_area > 0.0, f"Cap face area is zero at z={z}"

        section = mesh.section(plane_origin=[0.0, 0.0, z],
                               plane_normal=[0.0, 0.0, 1.0])
        if section is None:
            continue  # recorded: no section at this height for the mesh
        section_2d, _to_2d_matrix = section.to_2D()
        truth_area = float(section_2d.area)
        assert truth_area > 0.0, f"Section at z={z} has zero area"

        rel_err = abs(cap_area - truth_area) / truth_area
        assert rel_err <= 0.005, (
            f"Cap area {cap_area:.3f} mm^2 deviates from true section area "
            f"{truth_area:.3f} mm^2 (rel err {rel_err:.4f} > 0.005) at "
            f"z={z}; cap faces={int(cap_mask.sum())} tessellation of the "
            f"cut plane is wrong somewhere."
        )


# ---------------------------------------------------------------------------
# (f) Printed-material BVH chain: earlier chunks + tilted clip included.
# ---------------------------------------------------------------------------

def test_f_printed_model_includes_earlier_chunks_and_tilted_clip():
    aligned = _aligned_pipe_mesh()
    layer_height = 2.0

    capture = []

    engine_method = CollisionEngine.batch_check_poses_with_bvh

    def _capturing(self, points, normals, printed_bvh):
        capture.append(printed_bvh)
        return engine_method(self, points, normals, printed_bvh)

    CollisionEngine.batch_check_poses_with_bvh = _capturing
    try:
        result, diagnostics, _layers, _chunks = (
            GeometryApplicationService._execute_chunk_path(
                job_id="capture-run",
                aligned_mesh=aligned,
                job_mode=JobMode.INDEXED_MULTIDIRECTIONAL,
                job_settings={
                    "layer_height": layer_height,
                    "bed_center_z": BED_CENTER_Z,
                    "slice_planes": [dict(PLANE1), dict(PLANE2)],
                },
                machine_profile=MACHINE_PROFILE_DIRECT,
                layer_height=layer_height,
                bed_center_z=BED_CENTER_Z,
            )
        )
    finally:
        CollisionEngine.batch_check_poses_with_bvh = engine_method

    blocking = [d for d in diagnostics
                if d.status == DiagnosticStatus.FAIL]
    assert result.get("gcode_string"), (
        f"No gcode produced; blocking diagnostics: "
        f"{[(d.code, str(d.status)) for d in blocking]}"
    )

    assert len(capture) >= 2, (
        f"Expected batch_check_poses_with_bvh to be invoked for at least "
        f"chunks 1 and 2 ({len(capture)} captures at layer_height="
        f"{layer_height}); collision chain for tilted chunks not exercised."
    )

    printed_mesh = capture[-1].get_mesh()
    printed_v = np.asarray(printed_mesh.vertices, dtype=float)
    printed_f = np.asarray(printed_mesh.faces, dtype=np.int64)
    assert len(printed_v) > 0 and len(printed_f) > 0, (
        "Last captured printed-material BVH carries an empty mesh."
    )

    # A face lying flat on tilted plane 2 proves the clip that produced
    # the combined printed material happened against the TILTED plane.
    n2 = np.array(PLANE2["unit_normal"], dtype=float)
    o2 = np.array(PLANE2["plane_origin"], dtype=float)
    dots = (printed_v - o2) @ n2
    face_dots = dots[printed_f]
    spread = face_dots.max(axis=1) - face_dots.min(axis=1)
    on_plane_faces = int(np.count_nonzero(spread <= 2e-3))
    assert on_plane_faces > 0, (
        f"Combined printed mesh has no face flush with tilted plane 2 "
        f"(origin {tuple(PLANE2['plane_origin'])}, normal "
        f"{tuple(PLANE2['unit_normal'])}): the tilted clip is missing "
        f"from the printed-material model ({len(printed_f)} faces, "
        f"spreads min={spread.min():.4f})."
    )

    low_z_vertices = int(np.count_nonzero(printed_v[:, 2] < 40.0))
    assert low_z_vertices > 0, (
        f"Combined printed mesh has no vertex below z=40: earlier chunks "
        f"(chunk 0 spans the pipe below plane 1) are not part of the "
        f"printed material ({len(printed_v)} vertices, z range "
        f"[{printed_v[:, 2].min():.2f}, {printed_v[:, 2].max():.2f}])."
    )


# ---------------------------------------------------------------------------
# (l) Tilted-chunk pose rejection: current chunk's already-printed wall
#     must be included in collision checks for chunks >= 1.
# ---------------------------------------------------------------------------

def test_l_tilted_chunk_pose_rejection():
    """A nozzle pose whose holder end hits the current chunk's already-printed
    wall must be rejected as a collision. This verifies that chunks >= 1 check
    against the current chunk's already-printed part (not just earlier chunks).

    The test:
    1. Builds the printed-material BVH for earlier chunks (chunks 0 & 1).
    2. Clips the current chunk (chunk 2) at a mid-layer to get its
       already-printed part.
    3. Picks a clip vertex far from earlier chunks (distance > 2*holder_radius).
    4. Places the holder end within holder_radius of that vertex.
    5. Calls _check_chunk_ge_1_collision and asserts collision is detected.
    """
    from geometry_service import _check_chunk_ge_1_collision

    aligned = _aligned_pipe_mesh()

    from chunk_builder import build_capped_chunks, subtract_later_chunks
    from slice_plane_model import SlicePlane

    planes = [SlicePlane(**PLANE1), SlicePlane(**PLANE2)]
    chunks = build_capped_chunks(aligned, planes)
    chunks, _ = subtract_later_chunks("test-l", chunks)

    assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
    assert chunks[2] is not None, "Chunk 2 (tilted) must exist"

    # Align chunk 2 (the current chunk) to PLANE2
    local_mesh, matrix, min_z, max_z = align_chunk_to_slice_plane(
        chunks[2].copy(), SlicePlane(**PLANE2)
    )

    # Pick a layer in the middle of chunk 2's range
    layer_height = 2.0
    schedule = generate_layer_schedule(min_z, max_z, layer_height)
    assert len(schedule) > 0, "Chunk 2 must have layers"
    z = schedule[len(schedule) // 2]

    # --- Build earlier-chunks BVH (chunks 0 & 1 in world frame) ---
    earlier_chunks = [chunks[0], chunks[1]]
    combined_v = []
    combined_f = []
    face_offset = 0
    for prev_mesh in earlier_chunks:
        combined_v.append(prev_mesh.vertices)
        combined_f.append(prev_mesh.faces + face_offset)
        face_offset += len(prev_mesh.vertices)
    if combined_v:
        earlier_bvh = MeshBVH(vertices=np.vstack(combined_v), faces=np.vstack(combined_f))
    else:
        earlier_bvh = None

    # --- Clip current chunk below this layer (already-printed part) ---
    from collision import _trimesh_to_manifold, _manifold_to_trimesh_arrays

    m = _trimesh_to_manifold(local_mesh.vertices, local_mesh.faces)
    clip_below = m.trim_by_plane((0.0, 0.0, -1.0), -z)
    assert not clip_below.is_empty(), "Clip below layer must not be empty"

    clip_v, clip_f = _manifold_to_trimesh_arrays(clip_below)
    assert len(clip_f) > 0, "Clip must have faces"

    # Map clipped vertices to world frame
    mat = np.array(matrix, dtype=float).reshape(4, 4)
    clip_hom = np.column_stack([clip_v, np.ones(len(clip_v))])
    clip_world_hom = (mat @ clip_hom.T).T
    clip_world_v = clip_world_hom[:, :3] / clip_world_hom[:, 3:4]

    # --- Pick a clip vertex far from earlier chunks (> 2*holder_radius) ---
    # Query distances from clip vertices to earlier chunks BVH
    if earlier_bvh is not None:
        # Use a simple nearest-point query: find min distance from each clip vertex
        # to the earlier chunks mesh.
        earlier_mesh = earlier_bvh.get_mesh()
        # Compute distances from clip_world_v to earlier_mesh vertices (approximate)
        # For exact distance we'd use trimesh.proximity, but vertex-to-vertex
        # is a conservative upper bound. We just need ONE vertex that's far.
        # Let's compute min distance from each clip vertex to any earlier vertex.
        min_dists = np.full(len(clip_world_v), np.inf)
        for ev in earlier_mesh.vertices:
            d = np.linalg.norm(clip_world_v - ev, axis=1)
            min_dists = np.minimum(min_dists, d)
    else:
        min_dists = np.full(len(clip_world_v), np.inf)

    holder_radius = NOZZLE_HOLDER_RADIUS
    # Find vertices with distance > 2 * holder_radius
    far_mask = min_dists > (2 * holder_radius)
    assert np.any(far_mask), (
        f"No clip vertex found with distance to earlier chunks > "
        f"{2 * holder_radius:.2f} mm (max min_dist = {min_dists.max():.2f}). "
        f"Test setup needs a different layer or geometry."
    )
    # Pick the first far vertex
    far_idx = int(np.nonzero(far_mask)[0][0])
    far_vertex = clip_world_v[far_idx]

    # --- Build a nozzle pose with holder end within holder_radius of far_vertex ---
    # Local Z axis mapped to world = outward normal of the slice plane
    outward = (mat @ np.array([0.0, 0.0, 1.0, 0.0]))[:3]
    outward = outward / np.linalg.norm(outward)
    # Nozzle points toward the surface (normal = -outward)
    normal = -outward
    # Place tip so holder_end = far_vertex + offset (offset < holder_radius along normal)
    # holder_end = tip + normal * nozzle_length
    # We want ||holder_end - far_vertex|| < holder_radius
    # So: tip = far_vertex - normal * nozzle_length + normal * (holder_radius / 2)
    # Then holder_end = far_vertex + normal * (holder_radius / 2)
    offset = holder_radius / 2.0
    tip = far_vertex - normal * NOZZLE_LENGTH + normal * offset

    # Tip must be above bed (no bed collision)
    assert tip[2] > 0, f"Tip z={tip[2]:.3f} must be above bed_z={BED_CENTER_Z}"

    # Verify holder_end is within holder_radius of far_vertex
    holder_end = tip + normal * NOZZLE_LENGTH
    dist_to_far = np.linalg.norm(holder_end - far_vertex)
    assert dist_to_far < holder_radius, (
        f"Holder end distance to far_vertex = {dist_to_far:.3f}, "
        f"expected < {holder_radius:.3f}"
    )

    # --- Call the helper and assert collision is detected ---
    profile = SlicerMachineProfile(
        nozzle_length=NOZZLE_LENGTH,
        nozzle_holder_radius=holder_radius,
    )
    # Full-mesh BVH for the collision engine (used for bed collision check)
    part_bvh = MeshBVH(aligned.vertices, aligned.faces)
    engine = CollisionEngine(profile, part_bvh, bed_center_z=BED_CENTER_Z)

    points = tip.reshape(1, 3)
    normals_arr = normal.reshape(1, 3)

    # Call the helper directly
    collisions = _check_chunk_ge_1_collision(
        collision_engine=engine,
        pts_world=points,
        norms_world=normals_arr,
        local_mesh=local_mesh,
        mat=mat,
        z=z,
        profile=profile,
        cached_bvh=earlier_bvh,
    )

    assert collisions[0], (
        f"Expected collision when holder end is within {holder_radius:.1f} mm "
        f"of current chunk's already-printed wall at local z={z:.3f}. "
        f"Holder end distance to clip vertex = {dist_to_far:.3f} mm. "
        f"This verifies the current-chunk clip is included in the collision check."
    )


# ---------------------------------------------------------------------------
# (m) Bbox pruning soundness: pruned collision check must equal unpruned.
# ---------------------------------------------------------------------------

def test_m_bbox_prune_soundness():
    """The bbox early-out in _check_chunk_ge_1_collision must not change results.

    For 200 random poses (including poses just inside/outside expanded bboxes),
    the pruned result must exactly match an unpruned brute-force reference.
    """
    from geometry_service import _check_chunk_ge_1_collision

    aligned = _aligned_pipe_mesh()

    from chunk_builder import build_capped_chunks, subtract_later_chunks
    from slice_plane_model import SlicePlane

    planes = [SlicePlane(**PLANE1), SlicePlane(**PLANE2)]
    chunks = build_capped_chunks(aligned, planes)
    chunks, _ = subtract_later_chunks("test-m", chunks)

    assert len(chunks) == 3
    assert chunks[2] is not None

    # Align chunk 2 to PLANE2
    local_mesh, matrix, min_z, max_z = align_chunk_to_slice_plane(
        chunks[2].copy(), SlicePlane(**PLANE2)
    )

    # Pick a middle layer
    layer_height = 2.0
    schedule = generate_layer_schedule(min_z, max_z, layer_height)
    assert len(schedule) > 0
    z = schedule[len(schedule) // 2]

    # Build earlier-chunks BVH (chunks 0 & 1)
    earlier_chunks = [chunks[0], chunks[1]]
    combined_v = []
    combined_f = []
    face_offset = 0
    for prev_mesh in earlier_chunks:
        combined_v.append(prev_mesh.vertices)
        combined_f.append(prev_mesh.faces + face_offset)
        face_offset += len(prev_mesh.vertices)
    earlier_bvh = MeshBVH(vertices=np.vstack(combined_v), faces=np.vstack(combined_f))

    # Get clip BVH bounds to generate poses inside/outside
    mat = np.array(matrix, dtype=float).reshape(4, 4)
    clip_result = CollisionEngine(
        SlicerMachineProfile(nozzle_length=NOZZLE_LENGTH, nozzle_holder_radius=NOZZLE_HOLDER_RADIUS),
        MeshBVH(aligned.vertices, aligned.faces),
        bed_center_z=BED_CENTER_Z,
    )._clip_mesh_at_z(local_mesh.vertices, local_mesh.faces, z)
    assert clip_result is not None
    clip_v, clip_f = clip_result
    clip_hom = np.column_stack([clip_v, np.ones(len(clip_v))])
    clip_world_hom = (mat @ clip_hom.T).T
    clip_world_v = clip_world_hom[:, :3] / clip_world_hom[:, 3:4]
    clip_bvh = MeshBVH(vertices=clip_world_v, faces=clip_f)
    clip_mesh = clip_bvh.get_mesh()

    # Bboxes expanded by holder_radius
    holder_radius = NOZZLE_HOLDER_RADIUS
    earlier_mesh = earlier_bvh.get_mesh()
    earlier_min = earlier_mesh.bounds[0] - holder_radius
    earlier_max = earlier_mesh.bounds[1] + holder_radius
    clip_min = clip_mesh.bounds[0] - holder_radius
    clip_max = clip_mesh.bounds[1] + holder_radius

    # Outward normal (nozzle points along -outward)
    outward = (mat @ np.array([0.0, 0.0, 1.0, 0.0]))[:3]
    outward = outward / np.linalg.norm(outward)
    normal = -outward

    rng = np.random.default_rng(42)

    def random_point_in_bbox(bmin, bmax):
        return rng.uniform(bmin, bmax)

    def random_point_outside_bbox(bmin, bmax, margin=holder_radius):
        # Pick a face to be outside of
        face = rng.integers(0, 6)
        pt = rng.uniform(bmin, bmax)
        if face == 0: pt[0] = bmin[0] - margin - rng.uniform(0, 10)
        elif face == 1: pt[0] = bmax[0] + margin + rng.uniform(0, 10)
        elif face == 2: pt[1] = bmin[1] - margin - rng.uniform(0, 10)
        elif face == 3: pt[1] = bmax[1] + margin + rng.uniform(0, 10)
        elif face == 4: pt[2] = bmin[2] - margin - rng.uniform(0, 10)
        else: pt[2] = bmax[2] + margin + rng.uniform(0, 10)
        return pt

    # Generate 200 holder_end positions: mix of inside/outside both bboxes
    holder_ends = []
    for _ in range(50):
        holder_ends.append(random_point_in_bbox(earlier_min, earlier_max))
    for _ in range(50):
        holder_ends.append(random_point_outside_bbox(earlier_min, earlier_max))
    for _ in range(50):
        holder_ends.append(random_point_in_bbox(clip_min, clip_max))
    for _ in range(50):
        holder_ends.append(random_point_outside_bbox(clip_min, clip_max))
    holder_ends = np.array(holder_ends)

    # Convert to nozzle tips (tip = holder_end - normal * nozzle_length)
    tips = holder_ends - normal * NOZZLE_LENGTH
    normals_arr = np.tile(normal, (len(tips), 1))

    # Filter tips above bed
    above_bed = tips[:, 2] > 0
    tips = tips[above_bed]
    normals_arr = normals_arr[above_bed]
    holder_ends = holder_ends[above_bed]

    # Ensure we have enough poses
    assert len(tips) >= 100, f"Need enough poses above bed, got {len(tips)}"
    tips = tips[:200]
    normals_arr = normals_arr[:200]

    profile = SlicerMachineProfile(
        nozzle_length=NOZZLE_LENGTH,
        nozzle_holder_radius=holder_radius,
    )
    part_bvh = MeshBVH(aligned.vertices, aligned.faces)
    engine = CollisionEngine(profile, part_bvh, bed_center_z=BED_CENTER_Z)

    # --- Pruned result (current implementation) ---
    pruned = _check_chunk_ge_1_collision(
        collision_engine=engine,
        pts_world=tips,
        norms_world=normals_arr,
        local_mesh=local_mesh,
        mat=mat,
        z=z,
        profile=profile,
        cached_bvh=earlier_bvh,
    )

    # --- Unpruned brute-force reference ---
    # Build combined BVH (earlier + clip) and check all points against it
    clip_v, clip_f = clip_result
    clip_hom = np.column_stack([clip_v, np.ones(len(clip_v))])
    clip_world_hom = (mat @ clip_hom.T).T
    clip_world_v = clip_world_hom[:, :3] / clip_world_hom[:, 3:4]
    clip_bvh_ref = MeshBVH(vertices=clip_world_v, faces=clip_f)

    earlier_mesh_ref = earlier_bvh.get_mesh()
    combined_v_ref = np.vstack([earlier_mesh_ref.vertices, clip_world_v])
    combined_f_ref = np.vstack([
        earlier_mesh_ref.faces,
        clip_f + len(earlier_mesh_ref.vertices),
    ])
    combined_bvh = MeshBVH(vertices=combined_v_ref, faces=combined_f_ref)

    unpruned = engine.batch_check_poses_with_bvh(tips, normals_arr, combined_bvh)

    # Must match exactly
    diff = np.sum(pruned != unpruned)
    assert diff == 0, (
        f"Bbox pruning changed {diff}/{len(tips)} collision results! "
        f"Pruned: {pruned.sum()} collisions, Unpruned: {unpruned.sum()} collisions. "
        f"Mismatch indices: {np.where(pruned != unpruned)[0][:10]}"
    )

def test_g_chunk_metadata_and_single_S001(two_plane_direct):
    # (i) Partition: chunk layer ranges tile [0 .. len(layers)-1].
    layers_data = two_plane_direct["layers_data"]
    chunks_data = two_plane_direct["chunks_data"]
    ranges = _chunk_ranges(chunks_data)

    assert ranges[0][1] == 0, (
        f"First chunk must start at layer 0, got layer_idx_min="
        f"{ranges[0][1]} (ranges: {ranges})"
    )
    for k in range(1, len(ranges)):
        expected_start = ranges[k - 1][2] + 1
        assert ranges[k][1] == expected_start, (
            f"Chunk {ranges[k][0]} must start at layer "
            f"{expected_start} (directly after chunk {ranges[k-1][0]}), "
            f"got layer_idx_min={ranges[k][1]}; ranges={ranges}. "
            f"layer_idx_max is only written for the last chunk today."
        )
    last_max = ranges[-1][2]
    assert last_max == len(layers_data) - 1, (
        f"Last chunk must end at layer {len(layers_data) - 1}, "
        f"got {last_max}; ranges={ranges}"
    )
    empty_ranges = [r for r in ranges if r[2] < r[1]]
    assert not empty_ranges, f"Empty chunk layer ranges: {empty_ranges}"

    # (ii) Fail-fast collision run: tall column + short nozzle -> exactly
    # one failing S-001 diagnostic, no passing S-001 riding along.
    column = trimesh.creation.box(extents=(10.0, 10.0, 100.0))
    column.apply_translation([0.0, 0.0, 50.0])
    file_bytes = _stl_bytes_of(column)

    short_nozzle_profile = {
        "limits": {
            "nozzle_length": 3.0,
            "nozzle_holder_radius": 5.0,
            "ranges": BED_LIMITS,
        }
    }
    result, diagnostics = GeometryApplicationService.execute(
        job_id="tall-column",
        file_bytes=file_bytes,
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": LAYER_HEIGHT, "bed_center_z": BED_CENTER_Z},
        machine_profile=short_nozzle_profile,
    )

    s001 = [d for d in diagnostics if d.code == "S-001"]
    all_diag_report = [
        (d.code, str(d.status), d.message) for d in diagnostics
    ]
    assert len(s001) == 1, (
        f"Expected exactly one S-001 diagnostic for the short-nozzle "
        f"collision run, got {len(s001)} S-001 entries; full run "
        f"diagnostics: {all_diag_report}"
    )
    assert s001[0].status == DiagnosticStatus.FAIL, (
        f"The single S-001 must be a FAIL (collision halts the job), got "
        f"{s001[0].status!r} with message {s001[0].message!r}"
    )
    toolpath = result.get("toolpath_job", {})
    assert "error" in toolpath, (
        f"Collision must short-circuit the run with an error toolpath "
        f"payload, got keys {sorted(toolpath)}"
    )


# ---------------------------------------------------------------------------
# (h) Three-axis G-code perimeter follows the original section polygons.
# ---------------------------------------------------------------------------

_PLAYERS = (4, 40, 80)   # sampled production layer indices
_CORNER_TOL = 0.01       # mm
_EDGE_TOL = 0.01         # mm


def _layer_bucket_points(moves, z):
    """Indices of G-code moves falling on this layer's z (<= 5e-4 off)."""
    return [i for i, m in enumerate(moves) if abs(m["z"] - z) <= 5e-4]


def _rings_from_polygons(polygons):
    """Exterior rings (ndarrays, closing duplicate dropped), any geometry."""
    if polygons is None or polygons.is_empty:
        return []
    geoms = (list(polygons.geoms)
             if polygons.geom_type == "MultiPolygon" else [polygons])
    rings = []
    for geom in geoms:
        if geom.geom_type != "Polygon" or geom.is_empty:
            continue
        ring = np.asarray(geom.exterior.coords, dtype=float)[:-1]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def test_h_gcode_shell_geometry(single_plane_threeaxis_direct):
    h = LAYER_HEIGHT
    payload = single_plane_threeaxis_direct["result"].get("toolpath_job", {})
    gcode = payload.get("gcode_string", "")
    empty_run_diags = [
        (d.code, str(d.status))
        for d in single_plane_threeaxis_direct["diagnostics"]
    ]
    assert gcode, (
        f"No gcode_string in three-axis run; diagnostics: {empty_run_diags}"
    )
    moves = _parse_gcode_moves(gcode)
    assert moves, "No parsed motion lines in three-axis G-code"

    # For THREE_AXIS the base chunk plane is the default (0,0,1) plane
    # with identity local-to-world matrix and bed_center_z 0, so machine
    # X/Y/Z on the wire ARE the part-space layer points.
    aligned = _aligned_pipe_mesh()
    z_max = float(aligned.bounds[1][2])
    schedule = generate_layer_schedule(0.0, z_max, h)
    assert max(_PLAYERS) < len(schedule), (
        f"Schedule has {len(schedule)} layers, cannot sample indices "
        f"{_PLAYERS}"
    )
    partial = [
        i for i in range(len(moves) - 1)
        if not moves[i + 1]["is_travel"]
    ]
    next_in_run = {}
    prev_in_run = {}
    for i in partial:
        next_in_run[i] = i + 1
        prev_in_run[i + 1] = i

    for layer_idx in _PLAYERS:
        z = float(schedule[layer_idx])
        segment_ids = _layer_bucket_points(moves, z)
        if not segment_ids:
            continue  # empty layer in G-code; skip with knowledge
        segments = slice_mesh_at_z(aligned, z)
        polygons = reconstruct_polygons(segments)
        rings = _rings_from_polygons(polygons)
        if not rings:
            continue

        layer_pts = np.array([[moves[i]["x"], moves[i]["y"]] for i in segment_ids])
        # Travel-flagged destinations are also legitimate path vertices.
        for ring in rings:
            ring_xy = ring[:, :2]
            distances = np.linalg.norm(ring_xy[:, None, :] - layer_pts[None, :, :],
                                       axis=2)

            # Corner test: every original section-boundary vertex must be
            # visited by some G-code point on the same layer.
            corner_radii = distances.min(axis=1)
            worst_corner = float(corner_radii.max())
            assert worst_corner <= _CORNER_TOL, (
                f"Layer {layer_idx} (z={z}): worst G-code distance to an "
                f"original section vertex is {worst_corner:.4f} mm > "
                f"{_CORNER_TOL} mm. Perimeter points are not the section "
                f"boundary (resampled/inset shell geometry emitted "
                f"instead; {len(layer_pts)} G-code pts vs "
                f"{len(ring_xy)} ring vertices)."
            )

            # Edge-completeness: every consecutive ring-vertex pair must
            # appear as a consecutive print pair (order-insensitive).
            missing = []
            n_ring = len(ring_xy)
            for i in range(n_ring):
                a, b = ring_xy[i], ring_xy[(i + 1) % n_ring]
                candidates = set(
                    np.nonzero(np.linalg.norm(layer_pts - a, axis=1) <= _EDGE_TOL)[0]
                ) | set(
                    np.nonzero(np.linalg.norm(layer_pts - b, axis=1) <= _EDGE_TOL)[0]
                )
                matched = False
                for pos in candidates:
                    move_pos = segment_ids[pos]
                    for partner in (prev_in_run.get(move_pos),
                                    next_in_run.get(move_pos)):
                        if partner is None:
                            continue
                        partner_xy = np.array([moves[partner]["x"],
                                               moves[partner]["y"]])
                        match_a = np.linalg.norm(partner_xy - a) <= _EDGE_TOL
                        match_b = np.linalg.norm(partner_xy - b) <= _EDGE_TOL
                        if (match_a and
                                np.linalg.norm(layer_pts[pos] - b) <= _EDGE_TOL) or \
                           (match_b and
                                np.linalg.norm(layer_pts[pos] - a) <= _EDGE_TOL):
                            matched = True
                            break
                    if matched:
                        break
                if not matched:
                    missing.append((a.tolist(), b.tolist()))
            assert not missing, (
                f"Layer {layer_idx} (z={z}): {len(missing)}/{n_ring} "
                f"original section edges never appear as a consecutive "
                f"G-code print pair (first missing: {missing[:2]}). The "
                f"emitted perimeter does not follow the original "
                f"world-frame section polygon."
            )


# ---------------------------------------------------------------------------
# (i) Chunk metadata: contiguous partition, no gaps/overlaps, exact counts.
# ---------------------------------------------------------------------------

def test_i_chunk_metadata_no_gaps(two_plane_direct):
    layers_data = two_plane_direct["layers_data"]
    chunks_data = two_plane_direct["chunks_data"]

    layer_indices = [int(l["layer_idx"]) for l in layers_data]
    assert layer_indices == sorted(layer_indices), (
        "layers_data entries must be emitted with strictly increasing "
        "layer_idx (sequential schedule) in chunk order."
    )
    assert all(
        layer_indices[i] < layer_indices[i + 1]
        for i in range(len(layer_indices) - 1)
    ), "layer_idx values must be strictly increasing (no duplicates)."

    ranges = _chunk_ranges(chunks_data)
    for k, (idx, lo, hi) in enumerate(ranges):
        assert hi >= lo, (
            f"Chunk {idx} layer range [{lo}, {hi}] is empty/inverted"
        )
        if k + 1 < len(ranges):
            nlo = ranges[k + 1][1]
            assert nlo == hi + 1, (
                f"Chunk {ranges[k+1][0]} starts at layer {nlo} but chunk "
                f"{idx} ends at {hi}: gap/overlap in the partition "
                f"(ranges: {ranges})."
            )
    assert ranges[0][1] == 0, f"Partition must start at 0, got {ranges[0][1]}"
    assert ranges[-1][2] == len(layers_data) - 1, (
        f"Partition must end at {len(layers_data) - 1}, got "
        f"{ranges[-1][2]}; ranges={ranges}"
    )
    for idx, lo, hi in ranges:
        count = hi - lo + 1
        chunk_layer_count = sum(
            1 for l in layers_data if lo <= int(l["layer_idx"]) <= hi
        )
        assert chunk_layer_count == count, (
            f"Chunk {idx} claims {count} layers [{lo}, {hi}] but "
            f"layers_data holds {chunk_layer_count} in that window."
        )


# ---------------------------------------------------------------------------
# (j) Two-plane run completes in budget; BVH construction is amortized.
# ---------------------------------------------------------------------------

def test_j_two_plane_perf_and_bvh_reuse():
    aligned = _aligned_pipe_mesh()
    file_bytes = _stl_bytes_of(aligned)

    # 1) Wall-clock budget for the full execute() at production layer height.
    started = time.perf_counter()
    result, diagnostics_t = GeometryApplicationService.execute(
        job_id="perf-timing",
        file_bytes=file_bytes,
        job_mode=JobMode.INDEXED_MULTIDIRECTIONAL,
        job_settings={
            "layer_height": LAYER_HEIGHT,
            "bed_center_z": BED_CENTER_Z,
            "slice_planes": [dict(PLANE1), dict(PLANE2)],
        },
        machine_profile=MACHINE_PROFILE_DIRECT,
    )
    elapsed = time.perf_counter() - started
    assert result.get("toolpath_job", {}).get("gcode_string"), (
        f"Timing run produced no G-code; blocking diagnostics: "
        f"{[(d.code, str(d.status)) for d in diagnostics_t]}"
    )
    assert elapsed < 120.0, (
        f"Two-plane execute() took {elapsed:.1f}s > 120.0s budget at "
        f"layer_height={LAYER_HEIGHT} (chunks sliced in serial Python; "
        f"per-layer BVH rebuilds dominate)."
    )

    # 2) Structural: BVH construction must be amortized.
    # We expect one clip BVH per layer for chunks >= 1 (chunks 1 and 2),
    # plus a small constant overhead (part BVH, earlier-chunks BVHs).
    class _CountingMeshBVH(MeshBVH):
        instances_created = 0

        def __init__(self, vertices, faces):
            _CountingMeshBVH.instances_created += 1
            super().__init__(vertices, faces)

    original = geometry_service.MeshBVH
    geometry_service.MeshBVH = _CountingMeshBVH
    try:
        result2, diagnostics_c = (
            GeometryApplicationService.execute(
                job_id="perf-counting",
                file_bytes=file_bytes,
                job_mode=JobMode.INDEXED_MULTIDIRECTIONAL,
                job_settings={
                    "layer_height": 2.0,
                    "bed_center_z": BED_CENTER_Z,
                    "slice_planes": [dict(PLANE1), dict(PLANE2)],
                },
                machine_profile=MACHINE_PROFILE_DIRECT,
            )
        )
        bvh_count = _CountingMeshBVH.instances_created
    finally:
        geometry_service.MeshBVH = original

    assert result2.get("toolpath_job", {}).get("gcode_string"), (
        f"Counting run produced no G-code; blocking diagnostics: "
        f"{[(d.code, str(d.status)) for d in diagnostics_c]}"
    )

    # Compute expected layers in chunks >= 1 (chunks 1 and 2) at layer_height=2.0
    # Use a direct run to get chunk metadata without the counting wrapper.
    _, _, _, chunks_data = GeometryApplicationService._execute_chunk_path(
        job_id="meta-count",
        aligned_mesh=aligned,
        job_mode=JobMode.INDEXED_MULTIDIRECTIONAL,
        job_settings={
            "layer_height": 2.0,
            "bed_center_z": BED_CENTER_Z,
            "slice_planes": [dict(PLANE1), dict(PLANE2)],
        },
        machine_profile=MACHINE_PROFILE_DIRECT,
        layer_height=2.0,
        bed_center_z=BED_CENTER_Z,
    )
    layers_in_chunks_ge_1 = 0
    for c in chunks_data:
        if int(c["chunk_idx"]) >= 1:
            layers_in_chunks_ge_1 += int(c["layer_idx_max"]) - int(c["layer_idx_min"]) + 1

    # Allow: one clip BVH per layer in chunks >= 1, plus a small constant
    # for the part BVH, earlier-chunks BVHs, etc.
    max_allowed = layers_in_chunks_ge_1 + 5
    assert bvh_count <= max_allowed, (
        f"MeshBVH was constructed {bvh_count} times; expected <= {max_allowed} "
        f"(layers in chunks >= 1: {layers_in_chunks_ge_1} + 5). "
        f"Each layer in chunks >= 1 inherently needs its own clip BVH "
        f"because printed material differs per layer; this is expected."
    )


# ---------------------------------------------------------------------------
# (k) Diagnostics discipline.
# ---------------------------------------------------------------------------

def test_k_diagnostics_discipline():
    # (k1) Blocking preflight failure must NOT be accompanied by a
    # passing "S-001 Slicing completed." diagnostic.
    file_bytes = _pipe_stl_bytes()
    result_k1, diagnostics_k1 = GeometryApplicationService.execute(
        job_id="kh1-preflight-block",
        file_bytes=file_bytes,
        job_mode=JobMode.INDEXED_MULTIDIRECTIONAL,
        job_settings={
            "layer_height": LAYER_HEIGHT,
            "bed_center_z": BED_CENTER_Z,
            "slice_planes": [dict(PLANE_NO_HIT)],
        },
        machine_profile=MACHINE_PROFILE_DIRECT,
    )
    s001_pass = [
        d for d in diagnostics_k1
        if d.code == "S-001" and d.status == DiagnosticStatus.PASS
    ]
    assert not s001_pass, (
        f"A FAIL blocking preflight run still reported S-001 PASS "
        f"'Slicing completed.': diagnostics after a non-executed run: "
        f"{[(d.code, str(d.status), d.message) for d in diagnostics_k1]}"
    )
    blocking = [d for d in diagnostics_k1
                if d.status == DiagnosticStatus.FAIL]
    assert blocking, (
        f"Expected the preflight failure to emit a blocking FAIL "
        f"diagnostic; got {[(d.code, str(d.status)) for d in diagnostics_k1]}"
    )

    # (k2) Legacy slicer error path must emit S-001 FAIL.
    tiny_box = trimesh.creation.box(extents=(5.0, 5.0, 5.0))
    tiny_bytes = _stl_bytes_of(tiny_box)

    original_slice = geometry_service.slicer_python.slice_mesh

    def _legacy_boom(*args, **kwargs):
        return {"error": "legacy boom"}

    geometry_service.slicer_python.slice_mesh = _legacy_boom
    try:
        _result_k2, diagnostics_k2 = GeometryApplicationService.execute(
            job_id="kh2-legacy-error",
            file_bytes=tiny_bytes,
            job_mode="legacy_mode_probe",   # not in (THREE_AXIS, INDEXED) -> legacy branch
            job_settings={"layer_height": LAYER_HEIGHT, "bed_center_z": BED_CENTER_Z},
            machine_profile=MACHINE_PROFILE_DIRECT,
        )
    finally:
        geometry_service.slicer_python.slice_mesh = original_slice

    s001_fail = [
        d for d in diagnostics_k2
        if d.code == "S-001" and d.status == DiagnosticStatus.FAIL
    ]
    assert s001_fail, (
        f"Legacy slicer error ({{'error': 'legacy boom'}}) produced no "
        f"S-001 FAIL diagnostic; full diagnostics: "
        f"{[(d.code, str(d.status), d.message) for d in diagnostics_k2]}"
    )
