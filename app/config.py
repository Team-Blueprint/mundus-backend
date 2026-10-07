from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os
import dotenv


class Settings(BaseSettings):
    PROJECT_NAME: str = "Mundus Backend"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./mundus.db"

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    # Anti-fraud Geofence radius (meters)
    GEOFENCE_RADIUS_METERS: float = 100.0
    OVERDUE_THRESHOLD_DAYS: int = 10

    # Frontend Origin for deep links
    FRONTEND_ORIGIN: str = "https://usemundus.pxxl.click/contractor/sign-in"

    # Brevo Email Configuration
    BREVO_API_KEY: Optional[str] = None
    BREVO_SENDER_EMAIL: str = "noreply@mundus.org"
    BREVO_SENDER_NAME: str = "Mundus Waste Tracking"

    # Brevo / SMTP Configuration
    SMTP_HOST: Optional[str] = "smtp-relay.brevo.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # FCM Web Push
    FCM_SERVER_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()

