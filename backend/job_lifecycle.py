from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Job
from enums import JobStatus

class InvalidTransitionError(Exception):
    """Raised when a job attempts to transition in a way that violates the DAG."""
    pass

class JobLifecycle:
    """
    Manages state transitions for Jobs to ensure idempotent and strictly acyclic progressions.
    Valid transitions:
      PENDING -> RUNNING, CANCELLED
      RUNNING -> COMPLETE, FAILED, PARTIAL, CANCELLED
    """
    
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
        
    @classmethod
    def start_job(cls, db: Session, job: Job) -> Job:
        """Transitions a PENDING job to RUNNING."""
        if job.status == JobStatus.RUNNING:
            return job # Idempotent
            
        if job.status != JobStatus.PENDING:
            raise InvalidTransitionError(f"Cannot transition job from {job.status} to {JobStatus.RUNNING}")
            
        job.status = JobStatus.RUNNING
        job.started_at = cls._now()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def complete_job(cls, db: Session, job: Job) -> Job:
        """Transitions a RUNNING job to COMPLETE."""
        if job.status == JobStatus.COMPLETE:
            return job
            
        if job.status != JobStatus.RUNNING:
            raise InvalidTransitionError(f"Cannot transition job from {job.status} to {JobStatus.COMPLETE}")
            
        job.status = JobStatus.COMPLETE
        job.completed_at = cls._now()
        job.progress = 1.0
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def fail_job(cls, db: Session, job: Job) -> Job:
        """Transitions a RUNNING job to FAILED."""
        if job.status == JobStatus.FAILED:
            return job
            
        if job.status != JobStatus.RUNNING:
            raise InvalidTransitionError(f"Cannot transition job from {job.status} to {JobStatus.FAILED}")
            
        job.status = JobStatus.FAILED
        job.completed_at = cls._now()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def cancel_job(cls, db: Session, job: Job) -> Job:
        """Transitions a PENDING or RUNNING job to CANCELLED."""
        if job.status == JobStatus.CANCELLED:
            return job
            
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            raise InvalidTransitionError(f"Cannot transition job from {job.status} to {JobStatus.CANCELLED}")
            
        job.status = JobStatus.CANCELLED
        job.completed_at = cls._now()
        if not job.cancellation_requested_at:
            job.cancellation_requested_at = cls._now()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def partial_job(cls, db: Session, job: Job) -> Job:
        """Transitions a RUNNING job to PARTIAL."""
        if job.status == JobStatus.PARTIAL:
            return job
            
        if job.status != JobStatus.RUNNING:
            raise InvalidTransitionError(f"Cannot transition job from {job.status} to {JobStatus.PARTIAL}")
            
        job.status = JobStatus.PARTIAL
        job.completed_at = cls._now()
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
