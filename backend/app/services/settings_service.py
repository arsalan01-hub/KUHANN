"""System settings store (JSON values, audited writes)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.system import SystemSetting

DEFAULTS: dict[str, Any] = {
    "general.instance_name": "KUHHAN",
    "general.default_currency": "EUR",
    "general.default_language": "en",
    "general.support_email": "",
    "search.max_page_size": 200,
    "search.default_sort": "newest",
    "discovery.schedule": "daily",
    "discovery.max_inspect_per_run": 5,
    "discovery.search_api": {
        "enabled": False,
        "vendor": "brave",
        "endpoint": "https://api.search.brave.com/res/v1/web/search",
        "api_key_encrypted": None,
        "cx": "",
    },
    "collection.user_agent": "KUHHAAN-DiscoveryBot/1.0",
    "collection.request_delay_ms": 1500,
    "collection.max_listings_per_run": 200,
    "monitoring.new_listing_window_days": 7,
    "monitoring.default_saved_search_schedule": "daily",
    "notifications.email_enabled": False,
    "notifications.email_recipients": "",
    "risk.low_price_threshold_pct": 35,
    "risk.flag_threshold": 45,
    "backup.retention_days": 14,
    "backup.directory": "",
    "currency.rates_to_eur": {
        "EUR": 1.0,
        "USD": 0.92,
        "GBP": 1.18,
        "PLN": 0.232,
        "SEK": 0.088,
        "NOK": 0.086,
        "DKK": 0.134,
        "CZK": 0.040,
        "HUF": 0.0026,
        "RON": 0.201,
        "LTL": 0.29,
        "LVL": 1.42,
    },
}

SETTING_DESCRIPTIONS: dict[str, str] = {
    "general.instance_name": "Name shown in the interface and notification emails.",
    "general.default_currency": "Display currency for aggregated prices (original currencies are always kept).",
    "general.default_language": "Default interface language code.",
    "general.support_email": "Contact address shown to users.",
    "search.max_page_size": "Upper bound for a single search result page.",
    "search.default_sort": "Default ordering of search results.",
    "discovery.schedule": "How often the discovery engine searches for new websites.",
    "discovery.max_inspect_per_run": "How many newly discovered websites are inspected per run.",
    "discovery.search_api": "Configuration of the external search provider used by the discovery engine.",
    "collection.user_agent": "User agent sent by collectors when fetching a website.",
    "collection.request_delay_ms": "Delay between requests to the same website.",
    "collection.max_listings_per_run": "Safety cap on listings processed per collection run.",
    "monitoring.new_listing_window_days": "How long a listing counts as new.",
    "monitoring.default_saved_search_schedule": "Default monitoring interval for new saved searches.",
    "notifications.email_enabled": "Whether e-mail delivery is enabled (requires SMTP configuration).",
    "notifications.email_recipients": "Comma separated recipient list for operational alerts.",
    "risk.low_price_threshold_pct": "Percentage below the model average that raises a price warning.",
    "risk.flag_threshold": "Risk score at which a listing is flagged for review.",
    "backup.retention_days": "Backups older than this are pruned.",
    "backup.directory": "Absolute backup directory (empty = application default).",
    "currency.rates_to_eur": "Reference exchange rates used for aggregated price comparisons.",
}


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(SystemSetting, key)
    if row is not None:
        return row.value
    if key in DEFAULTS:
        return DEFAULTS[key]
    return default


def set_setting(db: Session, key: str, value: Any, *, user_id: str | None = None) -> SystemSetting:
    row = db.get(SystemSetting, key)
    now = datetime.now(timezone.utc)
    if row is None:
        row = SystemSetting(
            key=key,
            value=value,
            description=SETTING_DESCRIPTIONS.get(key, ""),
            updated_at=now,
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.value = value
        row.updated_at = now
        row.updated_by = user_id
    return row


def ensure_defaults(db: Session) -> None:
    now = datetime.now(timezone.utc)
    for key, value in DEFAULTS.items():
        if db.get(SystemSetting, key) is None:
            db.add(
                SystemSetting(
                    key=key,
                    value=value,
                    description=SETTING_DESCRIPTIONS.get(key, ""),
                    updated_at=now,
                )
            )
    db.flush()
