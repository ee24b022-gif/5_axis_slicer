import pytest
import time
import uuid
import asyncio
from concurrent.futures import Future

from local_executor import LocalJobExecutor
from enums import JobMode, JobStage

def test_job_cancelled_mid_flight():
    executor = LocalJobExecutor(max_workers=1)
    
    # We will submit a job that takes some time or gets blocked
    # Actually, we can submit a dummy job and then cancel it. 
    # Since slicing takes a split second, we might need a large mesh or we can just mock the cancel check.
    # But wait, local_executor launches an actual process running GeometryApplicationService.execute
    # Slicing a real mesh might be fast, but we can call cancel_job immediately after submit.
    # The cancel event should be seen either before CANONICAL_FRAME or SECTIONING.
    
    job_id = str(uuid.uuid4())
    
    # We need a minimal valid STL for it to parse without crashing
    import trimesh
    from io import BytesIO
    mesh = trimesh.creation.box((10,10,10))
    f = BytesIO()
    mesh.export(f, file_type='stl')
    file_bytes = f.getvalue()
    
    future = executor.submit_job(
        job_id=job_id,
        file_bytes=file_bytes,
        job_mode=JobMode.THREE_AXIS,
        job_settings={},
        machine_profile={},
        progress_callback=None
    )
    
    # Immediately cancel
    executor.cancel_job(job_id)
    
    # Wait for result
    res_payload, diagnostics = future.result()
    
    # Assert
    assert res_payload.get("status") == "cancelled"
    
    # Check that a diagnostic with code X-001 was emitted
    cancel_diag = next((d for d in diagnostics if d.code == "X-001"), None)
    assert cancel_diag is not None
    assert cancel_diag.message == "Job was cooperatively cancelled by user."
    
    executor.shutdown()
