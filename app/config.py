import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db.engine import build_database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    meta_verify_token: str = Field(validation_alias="META_VERIFY_TOKEN")
    meta_app_secret: str = Field(
        validation_alias=AliasChoices("META_APP_SECRET", "FACEBOOK_APP_SECRET")
    )
    meta_whatsapp_access_token: str = Field(
        validation_alias=AliasChoices(
            "META_WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_ACCESS_TOKEN",
            "FACEBOOK_ACCESS_TOKEN",
        )
    )
    whatsapp_phone_number_id: str = Field(
        validation_alias=AliasChoices(
            "WHATSAPP_PHONE_NUMBER_ID",
            "PHONE_NUMBER_ID",
        )
    )

    whatsapp_api_version: str = Field(
        default="v21.0", validation_alias="WHATSAPP_API_VERSION"
    )
    outbound_reply_enabled: bool = Field(
        default=True, validation_alias="OUTBOUND_REPLY_ENABLED"
    )
    idempotency_db_path: Path = Field(
        default_factory=lambda: Path(
            "/tmp/idempotency.db"
            if (
                os.getenv("VERCEL")
                or os.getenv("VERCEL_ENV")
                or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
            )
            else "./data/idempotency.db"
        ),
        validation_alias="IDEMPOTENCY_DB_PATH",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # When false, Postgres is disabled: funnel stage + idempotency use local SQLite only.
    database_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("DATABASE_ENABLED", "USE_POSTGRES"),
    )

    # PostgreSQL (Neon / Supabase / Railway). Optional: bot runs without DB until set.
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    # If DATABASE_URL breaks (password has @ # etc.), use these instead — no URL-encoding needed.
    database_host: str | None = Field(default=None, validation_alias="DATABASE_HOST")
    database_user: str = Field(default="postgres", validation_alias="DATABASE_USER")
    database_password: str | None = Field(
        default=None, validation_alias="DATABASE_PASSWORD"
    )
    database_name: str = Field(default="postgres", validation_alias="DATABASE_NAME")
    database_port: int = Field(default=5432, validation_alias="DATABASE_PORT")
    database_sslmode: str | None = Field(
        default="require", validation_alias="DATABASE_SSLMODE"
    )

    # If false, schema must exist (run: alembic upgrade head). Recommended for production.
    database_auto_create_tables: bool = Field(
        default=True,
        validation_alias="DATABASE_AUTO_CREATE_TABLES",
    )

    # Public WhatsApp line for branding / logs (change when you switch numbers in Meta).
    main_whatsapp_e164: str = Field(
        default="+918400437772",
        validation_alias="MAIN_WHATSAPP_E164",
    )

    @field_validator(
        "meta_verify_token",
        "meta_app_secret",
        "meta_whatsapp_access_token",
        "whatsapp_phone_number_id",
        mode="before",
    )
    @classmethod
    def _strip_whitespace(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        if not self.database_enabled:
            object.__setattr__(self, "database_url", None)
            return self
        if self.database_url and str(self.database_url).strip():
            return self
        if self.database_host and self.database_password is not None:
            object.__setattr__(
                self,
                "database_url",
                build_database_url(
                    host=self.database_host.strip(),
                    user=self.database_user,
                    password=self.database_password,
                    database=self.database_name,
                    port=self.database_port,
                    sslmode=self.database_sslmode,
                ),
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
