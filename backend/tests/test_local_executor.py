import pytest
import io
import trimesh
from enums import JobMode, JobStage
from local_executor import LocalJobExecutor

def create_valid_mesh_bytes():
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    f = io.BytesIO()
    mesh.export(f, file_type='stl')
    return f.getvalue()

def test_local_executor_dispatches_successfully():
    executor = LocalJobExecutor(max_workers=1)
    
    future = executor.submit_job(
        job_id="test_job_001",
        file_bytes=create_valid_mesh_bytes(),
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": 0.2, "bed_center_z": 0.0},
        machine_profile={}
    )
    
    # Wait for completion
    result, diagnostics = future.result(timeout=10)
    
    assert "toolpath_job" in result
    assert isinstance(diagnostics, list)
    
    executor.shutdown()

def test_local_executor_progress_events():
    executor = LocalJobExecutor(max_workers=1)
    
    emitted_events = []
    
    def on_progress(event):
        emitted_events.append(event)
        
    future = executor.submit_job(
        job_id="test_job_002",
        file_bytes=create_valid_mesh_bytes(),
        job_mode=JobMode.THREE_AXIS,
        job_settings={"layer_height": 0.2, "bed_center_z": 0.0},
        machine_profile={},
        progress_callback=on_progress
    )
    
    # Wait for completion
    future.result(timeout=10)
    
    # Wait briefly for callbacks to fire (add_done_callback happens after result)
    import time
    time.sleep(0.1)
    
    assert len(emitted_events) > 0
    assert emitted_events[0].job_id == "test_job_002"
    assert emitted_events[0].stage == JobStage.SECTIONING
    assert emitted_events[0].progress == 1.0
    
    executor.shutdown()
