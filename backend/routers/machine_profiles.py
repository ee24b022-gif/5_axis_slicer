import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dependencies import get_db
from models import MachineProfile
from schemas import MachineProfileResponse

router = APIRouter(prefix="/machine-profiles", tags=["machine-profiles"])

@router.get("", response_model=List[MachineProfileResponse])
def list_machine_profiles(db: Session = Depends(get_db)):
    """List all active machine profiles"""
    profiles = db.query(MachineProfile).filter(MachineProfile.is_active == True).all()
    return profiles

@router.get("/{profile_id}", response_model=MachineProfileResponse)
def get_machine_profile(profile_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific machine profile by ID (can be active or retired)"""
    profile = db.query(MachineProfile).filter(MachineProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Machine profile not found")
    return profile
