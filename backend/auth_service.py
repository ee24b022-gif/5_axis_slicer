import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
import hashlib
from config import settings
import secrets

ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token_string() -> str:
    """Generate a secure random string for a refresh token."""
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    """Hash a token for database storage."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def generate_api_key_pair() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns:
        prefix (str): An 8-character prefix used to identify the key.
        raw_key (str): The full raw API key (prefix + secret) to return to the user.
        hashed_secret (str): The SHA-256 hash of the full raw key for database storage.
    """
    secret = secrets.token_urlsafe(32)
    prefix = secrets.token_hex(4)  # 8 characters
    raw_key = f"{prefix}.{secret}"
    hashed_secret = hash_token(raw_key)
    return prefix, raw_key, hashed_secret
