from typing import Generator
from sqlalchemy.orm import Session
from database import SessionLocal

def get_db() -> Generator[Session, None, None]:
    """
    Dependency generator that yields an active SQLAlchemy Session.
    Ensures safe lifecycle closure and rollback upon termination.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader, SecurityScopes
import jwt
from jwt.exceptions import InvalidTokenError
from auth_service import ALGORITHM, hash_token
from config import settings
from models import User, APIKey
import uuid
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timezone

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

@dataclass
class Actor:
    actor_type: str  # "USER" or "MACHINE_KEY"
    user_id: uuid.UUID
    key_id: Optional[uuid.UUID]
    scopes: List[str]
    user: User

def get_current_actor(
    security_scopes: SecurityScopes,
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db)
) -> Actor:
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
        
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )

    # Allow skipping actual validation if testing without a DB/auth
    if settings.auth_mode == "none":
        user = db.query(User).first()
        if not user:
            raise credentials_exception
        return Actor(actor_type="USER", user_id=user.id, key_id=None, scopes=[], user=user)

    # 1. API Key Authentication
    if api_key:
        hashed_secret = hash_token(api_key)
        db_key = db.query(APIKey).filter(APIKey.key_hash == hashed_secret).first()
        
        if not db_key:
            raise credentials_exception
            
        now = datetime.utcnow()
        if db_key.revoked_at and db_key.revoked_at <= now:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key has been revoked")
        if db_key.expires_at and db_key.expires_at <= now:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key has expired")
            
        user = db.query(User).filter(User.id == db_key.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user for API key")
            
        # Enforce scopes
        if security_scopes.scopes:
            key_scopes = set(db_key.scopes)
            for scope in security_scopes.scopes:
                if scope not in key_scopes:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not enough permissions",
                        headers={"WWW-Authenticate": authenticate_value},
                    )
                    
        return Actor(actor_type="MACHINE_KEY", user_id=user.id, key_id=db_key.id, scopes=db_key.scopes, user=user)

    # 2. JWT Authentication
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (InvalidTokenError, ValueError):
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
        
    # Standard JWT has all implied scopes for now, or you could verify JWT scopes if they were included.
    return Actor(actor_type="USER", user_id=user.id, key_id=None, scopes=[], user=user)
