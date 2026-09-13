#!/bin/bash
# ============================================================
# Fixture Job Runner for Docker Compose Development Stack
# ============================================================
# Prerequisites:
#   docker compose up --build -d
#   Wait for API to be healthy (this script handles that)
#
# Usage:
#   bash scripts/run_fixture_job.sh
# ============================================================

set -e

API_BASE="${API_BASE:-http://localhost:8000}"
MAX_WAIT=60

echo "============================================"
echo " 5-Axis Slicer — Fixture Job Runner"
echo "============================================"
echo ""

# Step 0: Wait for API health
echo "[1/6] Waiting for API health check at ${API_BASE}/health ..."
elapsed=0
until curl -sf "${API_BASE}/health" > /dev/null 2>&1; do
  elapsed=$((elapsed + 1))
  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    echo "ERROR: API did not become healthy after ${MAX_WAIT}s"
    exit 1
  fi
  sleep 1
done
echo "  ✓ API is healthy."
echo ""

# Step 1: Register a test user
echo "[2/6] Registering test user..."
REGISTER_RESP=$(curl -sf -X POST "${API_BASE}/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "fixture_user",
    "email": "fixture@example.com",
    "password": "fixture_password_123"
  }' 2>/dev/null || true)

# Login to get access token
echo "[3/6] Logging in..."
LOGIN_RESP=$(curl -sf -X POST "${API_BASE}/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=fixture_user&password=fixture_password_123")

ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "ERROR: Failed to obtain access token."
  echo "Response: $LOGIN_RESP"
  exit 1
fi
echo "  ✓ Access token obtained."
echo ""

# Step 2: Generate a simple STL file and upload it
echo "[4/6] Generating and uploading test STL mesh..."

# Generate a minimal valid binary STL (a single triangle)
python3 -c "
import struct, sys, tempfile, os
header = b'\x00' * 80
num_triangles = 1
normal = struct.pack('<fff', 0.0, 0.0, 1.0)
v1 = struct.pack('<fff', 0.0, 0.0, 0.0)
v2 = struct.pack('<fff', 10.0, 0.0, 0.0)
v3 = struct.pack('<fff', 5.0, 10.0, 0.0)
attr = struct.pack('<H', 0)
data = header + struct.pack('<I', num_triangles) + normal + v1 + v2 + v3 + attr
path = '/tmp/fixture_test.stl'
with open(path, 'wb') as f:
    f.write(data)
print(path)
"

MESH_RESP=$(curl -sf -X POST "${API_BASE}/meshes" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -F "file=@/tmp/fixture_test.stl")

MESH_ID=$(echo "$MESH_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -z "$MESH_ID" ]; then
  echo "ERROR: Failed to upload mesh."
  echo "Response: $MESH_RESP"
  exit 1
fi
echo "  ✓ Mesh uploaded: ${MESH_ID}"
echo ""

# Step 3: Get machine profile ID
PROFILES_RESP=$(curl -sf "${API_BASE}/machine-profiles" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

PROFILE_ID=$(echo "$PROFILES_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
profiles = data if isinstance(data, list) else data.get('items', [])
if profiles:
    print(profiles[0]['id'])
else:
    print('')
" 2>/dev/null)

if [ -z "$PROFILE_ID" ]; then
  echo "ERROR: No machine profiles found."
  exit 1
fi
echo "  Using machine profile: ${PROFILE_ID}"

# Step 4: Submit a three-axis job
echo "[5/6] Submitting three-axis slicing job..."
JOB_RESP=$(curl -sf -X POST "${API_BASE}/jobs" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"mesh_id\": \"${MESH_ID}\",
    \"machine_profile_id\": \"${PROFILE_ID}\",
    \"mode\": \"three_axis\",
    \"settings\": {\"layer_height\": 0.2, \"bed_center_z\": 5.0}
  }")

JOB_ID=$(echo "$JOB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
  echo "ERROR: Failed to submit job."
  echo "Response: $JOB_RESP"
  exit 1
fi
echo "  ✓ Job submitted: ${JOB_ID}"
echo ""

# Step 5: Poll until terminal state
echo "[6/6] Polling job status..."
POLL_MAX=120
poll_elapsed=0

while true; do
  STATUS_RESP=$(curl -sf "${API_BASE}/jobs/${JOB_ID}" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}")

  STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  PROGRESS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(round(json.load(sys.stdin)['progress']*100))" 2>/dev/null)

  echo "  Status: ${STATUS} | Progress: ${PROGRESS}%"

  case "$STATUS" in
    complete|failed|cancelled|partial)
      break
      ;;
  esac

  poll_elapsed=$((poll_elapsed + 2))
  if [ "$poll_elapsed" -ge "$POLL_MAX" ]; then
    echo "ERROR: Job did not reach terminal state after ${POLL_MAX}s"
    exit 1
  fi
  sleep 2
done

echo ""
echo "============================================"
echo " RESULT: Job ${JOB_ID} → ${STATUS}"
echo "============================================"

# Fetch diagnostics
echo ""
echo "Diagnostics:"
DIAG_RESP=$(curl -sf "${API_BASE}/jobs/${JOB_ID}/diagnostics" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
echo "$DIAG_RESP" | python3 -c "
import sys, json
diags = json.load(sys.stdin)
if not diags:
    print('  (none)')
else:
    for d in diags:
        print(f'  [{d[\"stage\"]}] {d[\"severity\"]}: {d[\"code\"]} — {d[\"message\"]}')
" 2>/dev/null || echo "  (could not parse diagnostics)"

echo ""
echo "Done. Fixture job completed successfully!"
