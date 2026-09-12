from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Any, Callable
from enums import JobMode
from geometry_service import GeometryApplicationService
from progress_model import StageProgressEvent

def _worker_wrapper(job_id: str, file_bytes: bytes, job_mode: JobMode, job_settings: dict, machine_profile: dict, cancel_event=None) -> tuple:
    """
    Module-level function required for ProcessPoolExecutor serialization.
    """
    is_cancelled = (lambda: cancel_event.is_set()) if cancel_event else None
    return GeometryApplicationService.execute(
        job_id=job_id,
        file_bytes=file_bytes,
        job_mode=job_mode,
        job_settings=job_settings,
        machine_profile=machine_profile,
        progress_callback=None, # Progress callbacks don't cross process boundaries natively without pipes
        is_cancelled=is_cancelled
    )

from multiprocessing import Manager

class LocalJobExecutor:
    """
    A lightweight execution pool strictly for local development and testing.
    Offloads heavy geometric slicing to a background process.
    """
    def __init__(self, max_workers: int = 2):
        self.pool = ProcessPoolExecutor(max_workers=max_workers)
        self.manager = Manager()
        self._active_events = {}
        
    def submit_job(
        self,
        job_id: str,
        file_bytes: bytes,
        job_mode: JobMode,
        job_settings: dict,
        machine_profile: dict,
        progress_callback: Callable[[StageProgressEvent], None] = None
    ):
        """
        Submits the job for asynchronous execution.
        Returns a Future object that yields (result_payload, diagnostics).
        Note: Because of ProcessPool constraints, real-time progress events via callback
        are simulated or executed purely at the end of the future if running natively without Celery.
        """
        
        cancel_event = self.manager.Event()
        self._active_events[job_id] = cancel_event
        
        future = self.pool.submit(
            _worker_wrapper,
            job_id,
            file_bytes,
            job_mode,
            job_settings,
            machine_profile,
            cancel_event
        )
        
        # We can hook into the future to emit a final event
        if progress_callback:
            def on_done(f):
                try:
                    res_payload, _ = f.result()
                    self._active_events.pop(job_id, None)
                    
                    if res_payload.get("status") == "cancelled":
                        from enums import JobStage, JobStatus
                        # We might need to send a cancelled payload if requested, but for now just mark progress 1.0 (or partial)
                        # The executor tests will look at this. Let's just emit standard for now.
                        progress_callback(StageProgressEvent(
                            job_id=job_id,
                            stage=JobStage.SECTIONING,
                            progress=1.0 # Or maybe a different stage, but this is a mock callback anyway
                        ))
                    else:
                        from enums import JobStage
                        progress_callback(StageProgressEvent(
                            job_id=job_id,
                            stage=JobStage.SECTIONING,
                            progress=1.0
                        ))
                except Exception as e:
                    from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
                    progress_callback(StageProgressEvent(
                        job_id=job_id,
                        stage=JobStage.SECTIONING,
                        progress=0.0,
                        severity=DiagnosticSeverity.CRITICAL,
                        status=DiagnosticStatus.FAIL,
                        code="E-999",
                        message=f"Process crashed: {str(e)}"
                    ))
                    
            future.add_done_callback(on_done)
        else:
            def cleanup(f):
                self._active_events.pop(job_id, None)
            future.add_done_callback(cleanup)
            
        return future
    
    def cancel_job(self, job_id: str):
        if job_id in self._active_events:
            self._active_events[job_id].set()
    
    def shutdown(self, wait=True):
        self.pool.shutdown(wait=wait)
