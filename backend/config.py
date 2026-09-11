from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from typing import Optional

class Settings(BaseSettings):
    app_env: str = Field(default="local")
    
    database_url: str = Field(default="sqlite:///./open5x_local.db")
    redis_url: str = Field(default="redis://localhost:6379/0")
    artifact_storage_uri: str = Field(default="file:///tmp/open5x_artifacts")
    
    worker_concurrency: int = Field(default=4)
    artifact_retention_days: int = Field(default=7)
    upload_limit_mb: int = Field(default=50)
    auth_mode: str = Field(default="local")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_production_settings(self) -> 'Settings':
        if self.app_env == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production environment requires a non-SQLite database URL.")
            if "localhost" in self.redis_url or "127.0.0.1" in self.redis_url:
                raise ValueError("Production environment requires a remote Redis URL.")
            if self.artifact_storage_uri.startswith("file://"):
                raise ValueError("Production environment requires remote artifact storage (e.g., s3://).")
        return self

# Global settings instance
settings = Settings()
