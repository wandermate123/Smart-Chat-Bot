import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
            if os.getenv("VERCEL")
            else "./data/idempotency.db"
        ),
        validation_alias="IDEMPOTENCY_DB_PATH",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
