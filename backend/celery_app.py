import uuid
import os
from celery import Celery
from config import settings
from database import SessionLocal
from models import Job
from enums import JobStatus
from job_lifecycle import JobLifecycle
from storage import get_storage_adapter
from geometry_service import GeometryApplicationService
from progress_publisher import RedisProgressPublisher

celery_app = Celery(
    "slicer_worker",
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=settings.worker_concurrency,
    beat_schedule={
        "cleanup_expired_artifacts_daily": {
            "task": "trigger_artifact_cleanup",
            "schedule": 86400.0,
        }
    }
)

@celery_app.task(bind=True, name="execute_job_task")
def execute_job_task(self, job_id: str, mesh_storage_uri: str, job_mode: str, job_settings: dict, machine_profile_dict: dict):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if not job or job.status == JobStatus.CANCELLED:
            return {"status": "skipped", "reason": "Job not found or already cancelled"}
            
        JobLifecycle.start_job(db, job)
        
        # Load mesh bytes from storage
        storage = get_storage_adapter()
        mesh_bytes = storage.get_artifact(mesh_storage_uri)
        file_bytes = mesh_bytes
            
        # Optional: In a real system, we might periodically check self.request.called_directly 
        # or use a Redis flag for cancellation, but F-066 states cooperative cancellation is via DB
        # JobLifecycle.cancel_job will set cancellation_requested_at.
        def is_cancelled():
            # Refresh from db
            db.refresh(job)
            return job.cancellation_requested_at is not None

        # Initialize progress publisher
        publisher = RedisProgressPublisher()

        # Execute
        payload, diagnostics = GeometryApplicationService.execute(
            job_id=job_id,
            file_bytes=file_bytes,
            job_mode=job_mode,
            job_settings=job_settings,
            machine_profile=machine_profile_dict,
            progress_callback=publisher.publish,
            is_cancelled=is_cancelled
        )
        
        if payload.get("status") == "cancelled":
            JobLifecycle.cancel_job(db, job)
        else:
            JobLifecycle.complete_job(db, job)
            
        return {"status": "success", "payload_status": payload.get("status")}
        
    except Exception as e:
        if job:
            JobLifecycle.fail_job(db, job)
        raise e
        
    finally:
        db.close()

from datetime import datetime, timedelta, timezone
from models import Mesh, Export
from sqlalchemy import and_, not_, exists

@celery_app.task(bind=True, name="cleanup_mesh_artifact", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def cleanup_mesh_artifact(self, mesh_id: str):
    db = SessionLocal()
    try:
        mesh = db.query(Mesh).filter(Mesh.id == uuid.UUID(mesh_id)).first()
        if not mesh or mesh.cleaned_up_at is not None:
            return
            
        storage = get_storage_adapter()
        try:
            storage.delete_artifact(mesh.storage_uri)
        except FileNotFoundError:
            pass
            
        mesh.cleaned_up_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

@celery_app.task(bind=True, name="cleanup_export_artifact", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def cleanup_export_artifact(self, export_id: str):
    db = SessionLocal()
    try:
        export = db.query(Export).filter(Export.id == uuid.UUID(export_id)).first()
        if not export or export.cleaned_up_at is not None or not export.storage_uri:
            return
            
        storage = get_storage_adapter()
        try:
            storage.delete_artifact(export.storage_uri)
        except FileNotFoundError:
            pass
            
        export.cleaned_up_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()

@celery_app.task(name="trigger_artifact_cleanup")
def trigger_artifact_cleanup():
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.artifact_retention_days)
        
        recent_job_exists = exists().where(
            and_(
                Job.mesh_id == Mesh.id,
                Job.created_at >= cutoff
            )
        )
        
        eligible_meshes = db.query(Mesh).filter(
            Mesh.cleaned_up_at.is_(None),
            Mesh.created_at < cutoff,
            not_(recent_job_exists)
        ).all()
        
        for mesh in eligible_meshes:
            cleanup_mesh_artifact.delay(str(mesh.id))
            
        eligible_exports = db.query(Export).filter(
            Export.cleaned_up_at.is_(None),
            Export.created_at < cutoff
        ).all()
        
        for export in eligible_exports:
            cleanup_export_artifact.delay(str(export.id))
            
    finally:
        db.close()
