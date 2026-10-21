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
from celery.signals import setup_logging
from logging_config import setup_logging as custom_setup_logging

@setup_logging.connect
def config_loggers(*args, **kwags):
    custom_setup_logging()

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
    task_soft_time_limit=settings.task_soft_time_limit,
    task_time_limit=settings.task_time_limit,
    worker_max_memory_per_child=settings.worker_max_memory_per_child,
    worker_max_tasks_per_child=settings.worker_max_tasks_per_child,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "cleanup_expired_artifacts_daily": {
            "task": "trigger_artifact_cleanup",
            "schedule": 86400.0,
        }
    }
)

from celery.exceptions import SoftTimeLimitExceeded

@celery_app.task(bind=True, name="execute_job_task")
def execute_job_task(self, job_id: str, mesh_storage_uri: str, job_mode: str, job_settings: dict, machine_profile_dict: dict):
    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == uuid.UUID(job_id)).first()
        if not job or job.status == JobStatus.CANCELLED:
            return {"status": "skipped", "reason": "Job not found or already cancelled"}
            
        JobLifecycle.start_job(db, job)
        
        # Load mesh bytes from storage
        storage = get_storage_adapter()
        mesh_bytes = storage.get_artifact(mesh_storage_uri)
        file_bytes = mesh_bytes
            
        def is_cancelled():
            db.refresh(job)
            return job.cancellation_requested_at is not None

        publisher = RedisProgressPublisher()

        payload, diagnostics = GeometryApplicationService.execute(
            job_id=job_id,
            file_bytes=file_bytes,
            job_mode=job_mode,
            job_settings=job_settings,
            machine_profile=machine_profile_dict,
            progress_callback=publisher.publish,
            is_cancelled=is_cancelled
        )
        
        # Persist all diagnostics to the database
        from models import Diagnostic as DiagnosticModel
        from validation_model import ValidationResult
        for d in diagnostics:
            db.add(DiagnosticModel(
                job_id=uuid.UUID(job_id),
                stage=d.stage,
                severity=d.severity,
                status=d.status,
                code=d.code,
                message=d.message,
                details=d.details if d.details else None,
            ))
        db.commit()
        
        if payload.get("status") == "cancelled":
            JobLifecycle.cancel_job(db, job)
        else:
            # Check for blocking diagnostics or an error in the payload
            val_result = ValidationResult(diagnostics=diagnostics)
            toolpath = payload.get("toolpath_job", {})
            has_error = val_result.is_blocking or "error" in toolpath
            if has_error:
                JobLifecycle.fail_job(db, job)
            else:
                import hashlib
                from models import Chunk, Layer, Export
                from enums import ChunkValidity, ExportStatus

                layers_data = toolpath.get("_layers_data", [])
                chunks_data = toolpath.get("_chunks_data", [])
                job_uuid = uuid.UUID(job_id)

                for c in chunks_data:
                    db.add(Chunk(
                        job_id=job_uuid,
                        chunk_idx=c["chunk_idx"],
                        source_plane=c["source_plane"],
                        transform_matrix=c["transform_matrix"],
                        layer_idx_min=c["layer_idx_min"],
                        layer_idx_max=c["layer_idx_max"],
                        min_z=c["min_z"],
                        max_z=c["max_z"],
                        validity=ChunkValidity.VALID,
                        last_completed_layer=c["layer_idx_max"],
                        triangle_count=c.get("triangle_count", 0),
                        storage_key=c.get("storage_key", f"chunk_{c['chunk_idx']}")
                    ))

                for l in layers_data:
                    db.add(Layer(
                        job_id=job_uuid,
                        layer_idx=l["layer_idx"],
                        z_height=l["z_height"],
                        thickness=l["thickness"],
                        is_support=l.get("is_support", False)
                    ))

                gcode_str = toolpath.get("gcode_string", "")
                if gcode_str:
                    content = gcode_str.encode("utf-8")
                    content_hash = hashlib.sha256(content).hexdigest()
                    storage_uri = storage.save_artifact("exports", content, content_hash)

                    db.add(Export(
                        job_id=job_uuid,
                        creator_id=job.creator_id,
                        dialect=job.machine_profile.dialect,
                        status=ExportStatus.READY,
                        storage_uri=storage_uri,
                        content_hash=content_hash,
                        size_bytes=len(content),
                        export_metadata={"status": "ready", "safety_label": "PRODUCTION - VERIFIED"}
                    ))

                db.commit()
                JobLifecycle.complete_job(db, job)
            
        return {"status": "success", "payload_status": payload.get("status")}
        
    except SoftTimeLimitExceeded:
        if job:
            JobLifecycle.fail_job(db, job)
        return {"status": "failed", "reason": "Job execution timed out gracefully."}
        
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
