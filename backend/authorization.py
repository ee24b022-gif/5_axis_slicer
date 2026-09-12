from typing import Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from dependencies import Actor
from enums import UserRole
import uuid
from models import Job

def enforce_ownership(resource: Any, owner_field: str, actor: Actor, resource_name: str = "Resource"):
    """
    Checks if the given actor owns the resource, or has ADMIN bypass.
    Raises HTTPException 403 if they don't.
    """
    if getattr(actor.user, "role", None) == UserRole.ADMIN:
        return
        
    owner_id = getattr(resource, owner_field, None)
    if owner_id != actor.user_id:
        raise HTTPException(
            status_code=403, 
            detail=f"Not authorized to access this {resource_name}"
        )

def require_job_owner(job_id: uuid.UUID, db: Session, actor: Actor) -> Job:
    """
    Loads a job, checks 404, and enforces ownership (creator_id).
    Returns the Job object.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    enforce_ownership(job, "creator_id", actor, "Job")
    return job
