import uuid
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from dependencies import get_db, get_current_actor, Actor
from database import SessionLocal
from schemas import JobCreateRequest, JobResponse, DiagnosticResponse, PreviewResponse, ExportResponse
from models import Job, User, Diagnostic, Layer, Chunk, Export
from repositories import MeshRepository, BaseRepository
from models import MachineProfile
from enums import JobStatus, JobStage, DiagnosticSeverity, ExportStatus
from job_lifecycle import JobLifecycle
from storage import get_storage_adapter
from config import settings
import asyncio
import redis.asyncio as redis_async
from fastapi.responses import StreamingResponse
from enums import JobStage, DiagnosticSeverity, DiagnosticStatus
from export_gate import ExportGateService
from progress_model import StageProgressEvent
from authorization import require_job_owner, enforce_ownership
from release_gate import ReleaseGateService
from preprint_checklist import PreprintChecklist, ReleaseGateResult
router = APIRouter(prefix="/jobs", tags=["jobs"])

def _run_job_lifecycle(
    job_id: uuid.UUID,
    mesh_storage_uri: str,
    job_mode: str,
    job_settings: dict,
    machine_profile_dict: dict,
    executor: "LocalJobExecutor"
):
    """
    Runs in a FastAPI background thread.
    Manages DB lifecycle states and waits for LocalJobExecutor future.
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or job.status == JobStatus.CANCELLED:
            return
            
        JobLifecycle.start_job(db, job)
        
        # Load the mesh bytes from storage
        storage = get_storage_adapter()
        file_bytes = storage.get_artifact(mesh_storage_uri)

        # Submit to the multiprocess pool
        future = executor.submit_job(
            job_id=str(job_id),
            file_bytes=file_bytes,
            job_mode=job_mode,
            job_settings=job_settings,
            machine_profile=machine_profile_dict,
            progress_callback=None
        )
        
        # Block this background thread until the multiprocessing worker finishes
        try:
            payload, diagnostics = future.result()
            
            if payload.get("status") == "cancelled":
                JobLifecycle.cancel_job(db, job)
            else:
                JobLifecycle.complete_job(db, job)
                
        except Exception as e:
            JobLifecycle.fail_job(db, job)
            
    finally:
        db.close()

@router.post("", response_model=JobResponse, status_code=201)
def submit_job(
    request: Request,
    job_in: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    mesh_repo = MeshRepository(db)
    mesh = mesh_repo.get_by_id(job_in.mesh_id)
    if not mesh:
        raise HTTPException(status_code=404, detail="Mesh not found")
    if getattr(mesh, "cleaned_up_at", None):
        raise HTTPException(status_code=410, detail="Mesh artifact has been cleaned up and is no longer available")
        
    profile = db.query(MachineProfile).filter(MachineProfile.id == job_in.machine_profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Machine profile not found")
        
    job = Job(
        creator_id=current_actor.user_id,
        mesh_id=job_in.mesh_id,
        machine_profile_id=job_in.machine_profile_id,
        mode=job_in.mode,
        settings=job_in.settings,
        engine_revision="0.1.0",
        input_hash=mesh.content_hash,
        status=JobStatus.PENDING,
        progress=0.0
    )
    
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Enqueue work
    if settings.app_env == "production":
        from celery_app import execute_job_task
        execute_job_task.delay(
            str(job.id),
            mesh.storage_uri,
            job.mode,
            job.settings,
            {"contract": profile.contract, "limits": profile.limits}
        )
    else:
        executor = request.app.state.executor
        background_tasks.add_task(
            _run_job_lifecycle,
            job.id,
            mesh.storage_uri,
            job.mode,
            job.settings,
            {"contract": profile.contract, "limits": profile.limits},
            executor
        )
    
    return job

@router.get("/{job_id}", response_model=JobResponse)
def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    job = require_job_owner(job_id, db, current_actor)
    return job

@router.get("/{job_id}/events")
async def get_job_events(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    job = require_job_owner(job_id, db, current_actor)
        
    async def event_generator():
        terminal_states = {JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.PARTIAL}
        if job.status in terminal_states:
            event = StageProgressEvent(
                job_id=str(job.id),
                stage=JobStage.ARTIFACT_PERSISTENCE,
                progress=job.progress,
            )
            if job.status == JobStatus.FAILED:
                event.status = DiagnosticStatus.FAIL
                event.severity = DiagnosticSeverity.CRITICAL
                event.message = "Job failed."
            elif job.status == JobStatus.CANCELLED:
                event.status = DiagnosticStatus.WARNING
                event.severity = DiagnosticSeverity.WARNING
                event.message = "Job cancelled."
                
            yield f"data: {event.model_dump_json()}\n\n"
            return
            
        try:
            client = redis_async.from_url(settings.redis_url)
            
            # Replay latest state immediately
            latest_key = f"job_progress_latest:{job.id}"
            latest_payload = await client.get(latest_key)
            if latest_payload:
                if isinstance(latest_payload, bytes):
                    latest_payload = latest_payload.decode("utf-8")
                yield f"data: {latest_payload}\n\n"
            
            pubsub = client.pubsub()
            channel = f"job_progress:{job.id}"
            await pubsub.subscribe(channel)
            
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        yield f"data: {data}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.unsubscribe(channel)
                await client.aclose()
        except Exception as e:
            yield f"data: {{\"error\": \"Connection failed: {str(e)}\"}}\n\n"
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    job = require_job_owner(job_id, db, current_actor)
        
    job = JobLifecycle.cancel_job(db, job)
    
    # Signal executor to halt running processes
    executor = request.app.state.executor
    executor.cancel_job(str(job_id))
    
    return job

@router.get("/{job_id}/diagnostics", response_model=list[DiagnosticResponse])
def get_job_diagnostics(
    job_id: uuid.UUID,
    severity: Optional[DiagnosticSeverity] = None,
    stage: Optional[JobStage] = None,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    job = require_job_owner(job_id, db, current_actor)
        
    query = db.query(Diagnostic).filter(Diagnostic.job_id == job_id)
    if severity:
        query = query.filter(Diagnostic.severity == severity)
    if stage:
        query = query.filter(Diagnostic.stage == stage)
        
    query = query.order_by(Diagnostic.created_at.asc(), Diagnostic.id.asc())
    return query.all()

@router.get("/{job_id}/preview", response_model=PreviewResponse)
def get_job_preview(
    job_id: uuid.UUID,
    chunk_idx: Optional[int] = None,
    layer_idx_min: Optional[int] = None,
    layer_idx_max: Optional[int] = None,
    include_supports: bool = True,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    job = require_job_owner(job_id, db, current_actor)
        
    query = db.query(Layer).filter(Layer.job_id == job_id)
    
    if chunk_idx is not None:
        chunk = db.query(Chunk).filter(Chunk.job_id == job_id, Chunk.chunk_idx == chunk_idx).first()
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")
        query = query.filter(Layer.layer_idx >= chunk.layer_idx_min, Layer.layer_idx <= chunk.layer_idx_max)
        
    if layer_idx_min is not None:
        query = query.filter(Layer.layer_idx >= layer_idx_min)
    if layer_idx_max is not None:
        query = query.filter(Layer.layer_idx <= layer_idx_max)
        
    if not include_supports:
        query = query.filter(Layer.is_support == False)
        
    query = query.order_by(Layer.layer_idx.asc())
    layers = query.all()
    
    return {"job_id": job_id, "layers": layers}


@router.get("/{job_id}/export")
def get_job_export(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    job = require_job_owner(job_id, db, current_actor)
        
    export = db.query(Export).filter(Export.job_id == job_id).order_by(Export.created_at.desc()).first()
    if not export:
        raise HTTPException(status_code=404, detail="Export not found for this job")
        
    enforce_ownership(export, "creator_id", current_actor, "Export")
        
    if getattr(export, "cleaned_up_at", None):
        raise HTTPException(status_code=410, detail="Export artifact has been cleaned up and is no longer available")
        
    is_allowed, details = ExportGateService.evaluate(job, export)
    if not is_allowed:
        raise HTTPException(status_code=400, detail=details["reason"])
        
    if not export.storage_uri:
        raise HTTPException(status_code=404, detail="Export artifact storage URI missing")
        
    storage = get_storage_adapter()
    if not storage.exists(export.storage_uri):
        raise HTTPException(status_code=404, detail="Export artifact not found in storage")
        
    try:
        file_bytes = storage.get_artifact(export.storage_uri)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Export artifact not found in storage")
        
    from fastapi.responses import Response
    return Response(content=file_bytes, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename={export.id}.gcode"
    })

@router.post("/{job_id}/release-gate", response_model=ReleaseGateResult)
def evaluate_release_gate(
    job_id: uuid.UUID,
    checklist: PreprintChecklist,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    """
    Evaluate the release gate for a job. Requires a completed pre-print
    physical dry-run checklist. This endpoint does NOT trigger a download —
    the operator must separately call GET /jobs/{job_id}/export after
    authorization.
    """
    job = require_job_owner(job_id, db, current_actor)
    
    export = db.query(Export).filter(Export.job_id == job_id).order_by(Export.created_at.desc()).first()
    if not export:
        raise HTTPException(status_code=404, detail="Export not found for this job")
    
    enforce_ownership(export, "creator_id", current_actor, "Export")
    
    result = ReleaseGateService.evaluate(job, export, checklist)
    return result
