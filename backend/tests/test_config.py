import pytest
from pydantic import ValidationError
from config import Settings
import os

def test_local_defaults():
    # Instantiating Settings without environment variables should work (local defaults)
    # We clear env vars that might interfere just in case
    old_env = os.environ.get("APP_ENV")
    if "APP_ENV" in os.environ:
        del os.environ["APP_ENV"]
        
    settings = Settings()
    assert settings.app_env == "local"
    assert settings.database_url == "sqlite:///./open5x_local.db"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.artifact_storage_uri == "file:///tmp/open5x_artifacts"
    
    if old_env is not None:
        os.environ["APP_ENV"] = old_env

def test_production_fails_with_local_defaults():
    # If app_env is production but we use local defaults, it should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="production")
    
    err_str = str(exc_info.value)
    assert "Production environment requires a non-SQLite database URL" in err_str

def test_production_succeeds_with_valid_urls():
    # Valid production settings should pass
    settings = Settings(
        app_env="production",
        database_url="postgresql://user:pass@db:5432/open5x",
        redis_url="redis://cache:6379/0",
        artifact_storage_uri="s3://bucket/artifacts"
    )
    assert settings.app_env == "production"
    assert settings.database_url == "postgresql://user:pass@db:5432/open5x"
