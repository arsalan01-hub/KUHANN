"""Connector registry — the only place that knows which connector keys exist."""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.connectors.base import (
    ApiIntegrationConnector,
    BaseConnector,
    ConnectorError,
    HtmlListingConnector,
    JsonFeedConnector,
)
from app.models.source import WebsiteSource

CONNECTORS: dict[str, type[BaseConnector]] = {
    JsonFeedConnector.key: JsonFeedConnector,
    HtmlListingConnector.key: HtmlListingConnector,
    ApiIntegrationConnector.key: ApiIntegrationConnector,
}

DEFAULT_KEY_BY_METHOD = {
    "feed": JsonFeedConnector.key,
    "html": HtmlListingConnector.key,
    "api": ApiIntegrationConnector.key,
}


def connector_catalogue() -> list[dict]:
    return [
        {
            "key": cls.key,
            "label": cls.label,
            "required_config": list(cls.required_config),
        }
        for cls in CONNECTORS.values()
    ]


def get_connector(
    db: Session, source: WebsiteSource, client: httpx.Client | None = None
) -> BaseConnector:
    key = source.connector_key or DEFAULT_KEY_BY_METHOD.get(source.access_method)
    if not key:
        raise ConnectorError(
            "This website has no automated connector configured. "
            "Use it in manual mode or configure a connector."
        )
    cls = CONNECTORS.get(key)
    if cls is None:
        raise ConnectorError(f"Unknown connector '{key}'")
    return cls(db, source, client)
