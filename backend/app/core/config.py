"""Application configuration.

All values are read from environment variables so that the same code runs in the
Base44 sandbox preview and on a production Linux VPS without changes.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_name: str = "KUHHAN"
    environment: str = "development"
    api_prefix: str = "/api"

    # --- security -----------------------------------------------------------
    secret_key: str = "dev-insecure-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 720
    # Fernet key for API credential encryption. When empty, a key is derived
    # from SECRET_KEY (development convenience, documented in .env.example).
    encryption_key: str = ""
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60

    # --- database -----------------------------------------------------------
    database_url: str = "postgresql+psycopg://kuhhan:kuhhan@localhost:5432/kuhhan"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800

    # --- bootstrap ----------------------------------------------------------
    admin_email: str = "admin@kuhhan.local"
    admin_password: str = "KuhhanDev!2026"
    admin_name: str = "KUHHAN Administrator"
    seed_source_catalogue: bool = True

    # --- outbound HTTP (discovery / connectors) -----------------------------
    outbound_timeout_seconds: float = 15.0
    outbound_user_agent: str = "KUHHAAN-DiscoveryBot/1.0 (+https://kuhhan.example/bot)"
    outbound_max_bytes: int = 2_000_000
    outbound_max_redirects: int = 3
    allow_private_outbound: bool = False

    # --- runtime ------------------------------------------------------------
    cors_origins: str = ""
    worker_poll_seconds: int = 15
    worker_heartbeat_seconds: int = 30
    backup_dir: str = "/workspace/backend/var/backups"
    backup_retention_days: int = 14
    preview_token_in_logs: bool = False

    @property
    def preview_mode(self) -> bool:
        """True only when the Base44 sandbox marks this as a preview run."""
        return os.environ.get("BASE44_PREVIEW_MODE") == "1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
