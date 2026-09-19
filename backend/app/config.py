from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DUDRI_", env_file=Path(__file__).resolve().parents[2] / ".env", env_file_encoding="utf-8-sig", extra="ignore", hide_input_in_errors=True)
    environment: Literal["development", "test", "production"] = "development"
    local_demo_enabled: bool = False
    project_root: Path = Path(__file__).resolve().parents[2]
    database_url: str = "sqlite:///./.data/dudri.db"
    app_origin: str = "http://localhost:3000"
    site_origin: str = "http://127.0.0.1:8001"
    storage_path: Path = Path(".data/objects")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    smtp_starttls: bool = True
    github_client_id: str = ""
    github_client_secret: str = ""
    credential_encryption_key: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = "https://ai.cs.kookmin.ac.kr/v1"
    ai_easy_model: str = ""
    ai_hard_model: str = ""
    ai_timeout_seconds: int = 180
    upload_max_bytes: int | None = None
    source_retention_days: int | None = None
    external_ai_consent_text: str = ""

    @model_validator(mode="after")
    def production_configuration(self):
        if self.app_origin == self.site_origin:
            raise ValueError("Generated sites must use a separate origin")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if not self.credential_encryption_key or not self.smtp_host:
                raise ValueError("Production requires credential encryption and SMTP configuration")
            if not self.app_origin.startswith("https://") or not self.site_origin.startswith("https://"):
                raise ValueError("Production origins must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
