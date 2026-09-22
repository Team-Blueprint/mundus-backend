from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
import dotenv


class Settings(BaseSettings):
    PROJECT_NAME: str = "Mundus Backend"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./mundus.db"

    # Auth
    SECRET_KEY: str = os.environ.get("SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    # Anti-fraud Geofence radius (meters)
    GEOFENCE_RADIUS_METERS: float = 100.0
    OVERDUE_THRESHOLD_DAYS: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()

