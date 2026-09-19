from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
LOCAL_DATABASE_URL = f"sqlite:///{(ROOT / 'backend/.data/dudri.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DUDRI_", env_file=Path(__file__).resolve().parents[2] / ".env", env_file_encoding="utf-8-sig", extra="ignore", hide_input_in_errors=True)
    environment: Literal["development", "test", "production"] = "development"
    service_role: Literal["app", "api", "sites"] = "app"
    local_demo_enabled: bool = False
    project_root: Path = Path(__file__).resolve().parents[2]
    database_url: str = Field(default=LOCAL_DATABASE_URL, repr=False)
    app_origin: str = "http://localhost:3000"
    site_origin: str = "http://127.0.0.1:8001"
    storage_path: Path = Path(".data/objects")
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_sender: str = ""
    smtp_starttls: bool = True
    github_client_id: str = ""
    github_client_secret: str = Field(default="", repr=False)
    credential_encryption_key: str = Field(default="", repr=False)
    ai_api_key: str = Field(default="", repr=False)
    ai_model: str = ""
    ai_base_url: str = "https://ai.cs.kookmin.ac.kr/v1"
    ai_easy_model: str = ""
    ai_hard_model: str = ""
    ai_timeout_seconds: int = 180
    upload_max_bytes: int | None = None
    source_retention_days: int | None = None
    external_ai_consent_text: str = ""

    @field_validator("app_origin", "site_origin")
    @classmethod
    def canonical_origin(cls, value):
        try:
            url = urlsplit(value.strip())
            if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
                raise ValueError
            host = f"[{url.hostname}]" if ":" in url.hostname else url.hostname
            port = url.port
            suffix = f":{port}" if port and port != (443 if url.scheme == "https" else 80) else ""
            return f"{url.scheme}://{host}{suffix}"
        except ValueError:
            raise ValueError("Use an HTTP(S) origin without a path, query, or credentials") from None

    @field_validator("database_url", mode="before")
    @classmethod
    def database_connection(cls, value):
        value = (value or "").strip() or LOCAL_DATABASE_URL
        try:
            url = make_url(value)
            if url.drivername in ("postgres", "postgresql", "postgresql+psycopg"):
                return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
            if url.drivername == "sqlite":
                return value
        except Exception:
            pass
        raise ValueError("Use a PostgreSQL connection URI or a SQLite URL")

    @model_validator(mode="after")
    def production_configuration(self):
        if self.app_origin == self.site_origin:
            raise ValueError("Generated sites must use a separate origin")
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if self.service_role != "sites" and (not self.credential_encryption_key or not self.smtp_host or not self.smtp_sender):
                raise ValueError("Production app requires credential encryption and SMTP host/sender configuration")
            if not self.site_origin.startswith("https://") or (self.service_role != "sites" and not self.app_origin.startswith("https://")):
                raise ValueError("Production origins must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
