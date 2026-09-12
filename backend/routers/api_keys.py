from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List
import uuid

from dependencies import get_db, get_current_actor, Actor
from models import APIKey
from schemas import APIKeyCreateRequest, APIKeyResponse, APIKeyCreateResponse
from auth_service import generate_api_key_pair

router = APIRouter(prefix="/auth/api-keys", tags=["auth", "api-keys"])

@router.post("", response_model=APIKeyCreateResponse)
def create_api_key(
    request: APIKeyCreateRequest,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    prefix, raw_key, hashed_secret = generate_api_key_pair()
    
    expires_at = None
    if request.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)
        
    db_key = APIKey(
        user_id=current_actor.user_id,
        key_hash=hashed_secret,
        prefix=prefix,
        scopes=request.scopes,
        expires_at=expires_at,
        description=request.description
    )
    
    db.add(db_key)
    db.commit()
    db.refresh(db_key)
    
    response_data = APIKeyResponse.model_validate(db_key).model_dump()
    response_data["raw_key"] = raw_key
    return APIKeyCreateResponse(**response_data)

@router.get("", response_model=List[APIKeyResponse])
def list_api_keys(
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    keys = db.query(APIKey).filter(APIKey.user_id == current_actor.user_id).all()
    return keys

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_actor: Actor = Depends(get_current_actor)
):
    db_key = db.query(APIKey).filter(
        APIKey.id == key_id, 
        APIKey.user_id == current_actor.user_id
    ).first()
    
    if not db_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key not found")
        
    if db_key.revoked_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API Key is already revoked")
        
    db_key.revoked_at = datetime.utcnow()
    db.commit()
    return None
