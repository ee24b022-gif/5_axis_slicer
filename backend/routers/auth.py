from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from dependencies import get_db, get_current_actor, Actor
from models import User, RefreshToken
from enums import UserRole
from auth_service import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token_string,
    hash_token
)
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    role: Optional[str] = UserRole.USER.value
    is_active: bool

@router.post("/login", response_model=Token)
def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        (User.username == form_data.username) | (User.email == form_data.username)
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    refresh_token_str = create_refresh_token_string()
    refresh_token_hashed = hash_token(refresh_token_str)

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=refresh_token_hashed,
        expires_at=expires_at
    )
    db.add(db_refresh_token)
    db.commit()

    response.set_cookie(
        key="refresh_token",
        value=refresh_token_str,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh", response_model=Token)
def refresh_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    refresh_token_str = request.cookies.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    refresh_token_hashed = hash_token(refresh_token_str)

    db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == refresh_token_hashed).first()

    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if db_token.revoked_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db_token.user
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    db_token.revoked_at = datetime.now(timezone.utc)

    new_refresh_token_str = create_refresh_token_string()
    new_refresh_token_hashed = hash_token(new_refresh_token_str)
    new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=new_refresh_token_hashed,
        expires_at=new_expires_at,
        replaced_by_id=db_token.id
    )
    db.add(new_db_token)
    db.commit()
    db.refresh(new_db_token)

    db_token.replaced_by_id = new_db_token.id
    db.commit()

    access_token = create_access_token(data={"sub": str(user.id)})

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token_str,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    refresh_token_str = request.cookies.get("refresh_token")
    if refresh_token_str:
        refresh_token_hashed = hash_token(refresh_token_str)
        db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == refresh_token_hashed).first()
        if db_token and not db_token.revoked_at:
            db_token.revoked_at = datetime.now(timezone.utc)
            db.commit()

    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserResponse)
def get_me(current_actor: Actor = Depends(get_current_actor)):
    return current_actor.user