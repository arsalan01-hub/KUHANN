"""Website connector framework.

A connector turns one permitted access method (official API, public feed,
permitted HTML page) into normalised listing dictionaries. New connectors are
registered in ``registry.py``; the search engine and collectors never need to
change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.models.api import ApiIntegration
from app.models.source import WebsiteSource
from app.services import api_sync
from app.services.http import OutboundError, safe_request


class ConnectorError(Exception):
    """Raised when a connector cannot legally or technically collect."""


@dataclass
class ConnectorReport:
    listings: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pages: int = 0


class BaseConnector(ABC):
    key: str = "base"
    label: str = "Base connector"
    required_config: tuple[str, ...] = ()

    def __init__(self, db: Session, source: WebsiteSource, client: httpx.Client | None = None):
        self.db = db
        self.source = source
        self.client = client
        self.config: dict[str, Any] = dict(source.connector_config or {})

    def validate_config(self) -> list[str]:
        return [f"Missing configuration '{key}'" for key in self.required_config if not self.config.get(key)]

    @abstractmethod
    def fetch(self, *, criteria: dict[str, Any] | None = None, limit: int = 100) -> ConnectorReport:
        ...

    def test(self) -> dict[str, Any]:
        problems = self.validate_config()
        if problems:
            return {"ok": False, "message": "; ".join(problems), "sample": None}
        try:
            report = self.fetch(limit=5)
        except (ConnectorError, OutboundError) as exc:
            return {"ok": False, "message": str(exc), "sample": None}
        return {
            "ok": bool(report.listings),
            "message": f"{len(report.listings)} listing(s) parsed"
            + (f"; {'; '.join(report.notes)}" if report.notes else ""),
            "sample": report.listings[0] if report.listings else None,
        }


class JsonFeedConnector(BaseConnector):
    """Public JSON/REST feed with a declarative field map."""

    key = "json_feed"
    label = "Public JSON feed"
    required_config = ("feed_url", "field_map")

    def fetch(self, *, criteria: dict[str, Any] | None = None, limit: int = 100) -> ConnectorReport:
        report = ConnectorReport()
        response = safe_request("GET", self.config["feed_url"], client=self.client)
        if response.status_code >= 400:
            raise ConnectorError(f"Feed returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError("Feed did not return JSON") from exc
        records = api_sync.resolve_path(payload, self.config.get("records_path")) if self.config.get("records_path") else payload
        if isinstance(records, dict):
            for key in ("results", "items", "data", "listings", "vehicles"):
                if isinstance(records.get(key), list):
                    records = records[key]
                    break
        if not isinstance(records, list):
            raise ConnectorError("Configured records path did not resolve to a list")
        report.pages = 1
        field_map: dict[str, str] = dict(self.config.get("field_map") or {})
        defaults: dict[str, Any] = dict(self.config.get("defaults") or {})
        for record in records[:limit]:
            if not isinstance(record, dict):
                continue
            mapped: dict[str, Any] = {}
            for kuhhan_field, path in field_map.items():
                if kuhhan_field.startswith("_"):
                    continue
                value = api_sync.resolve_path(record, path)
                if value not in (None, ""):
                    mapped[kuhhan_field] = value
            for key, value in defaults.items():
                mapped.setdefault(key, value)
            if mapped:
                report.listings.append(mapped)
        report.notes.append(f"{len(records)} record(s) in feed, {len(report.listings)} mapped")
        return report


class HtmlListingConnector(BaseConnector):
    """Permitted HTML listing page with CSS selectors configured per source."""

    key = "html_listing"
    label = "HTML listing page"
    required_config = ("listing_url", "item_selector", "fields")

    def validate_config(self) -> list[str]:
        problems = super().validate_config()
        if not isinstance(self.config.get("fields"), dict) or not self.config.get("fields"):
            problems.append("Field selectors are required")
        return problems

    def fetch(self, *, criteria: dict[str, Any] | None = None, limit: int = 100) -> ConnectorReport:
        if self.source.robots_allows_crawl is False:
            raise ConnectorError(
                "robots.txt does not permit automated crawling of this website. "
                "Switch the source to manual access instead."
            )
        report = ConnectorReport()
        max_pages = int(self.config.get("max_pages") or 1)
        url = self.config["listing_url"]
        for page in range(1, max_pages + 1):
            response = safe_request("GET", url, client=self.client)
            if response.status_code >= 400:
                raise ConnectorError(f"Listing page returned HTTP {response.status_code}")
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select(self.config["item_selector"])
            report.pages += 1
            if not items:
                report.notes.append(f"No items matched '{self.config['item_selector']}' on page {page}")
                break
            for item in items:
                if len(report.listings) >= limit:
                    break
                mapped = self._extract(item)
                if mapped:
                    report.listings.append(mapped)
            next_selector = self.config.get("next_page_selector")
            if not next_selector:
                break
            next_link = soup.select_one(next_selector)
            if not next_link or not next_link.get("href"):
                break
            from urllib.parse import urljoin

            url = urljoin(url, str(next_link["href"]))
        report.notes.append(f"{len(report.listings)} listing(s) parsed from {report.pages} page(s)")
        return report

    def _extract(self, node) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        fields: dict[str, Any] = dict(self.config.get("fields") or {})
        for kuhhan_field, spec in fields.items():
            if isinstance(spec, str):
                selector, attribute = spec, "text"
            elif isinstance(spec, dict):
                selector = spec.get("selector", "")
                attribute = spec.get("attr", "text")
            else:
                continue
            element = node.select_one(selector) if selector else node
            if element is None:
                continue
            if attribute == "text":
                value = element.get_text(" ", strip=True)
            elif attribute == "href":
                value = element.get("href")
            else:
                value = element.get(attribute)
            if value:
                mapped[kuhhan_field] = str(value).strip()
        link_spec = self.config.get("link_selector")
        if link_spec and "original_url" not in mapped:
            element = node.select_one(link_spec) if isinstance(link_spec, str) else None
            href = element.get("href") if element else None
            if href:
                from urllib.parse import urljoin

                base = self.config.get("listing_url") or self.source.homepage_url
                mapped["original_url"] = urljoin(base, str(href))
        external = self.config.get("external_id_selector")
        if external:
            element = node.select_one(external) if isinstance(external, str) else None
            if element is not None:
                mapped["external_id"] = element.get("data-id") or element.get_text(strip=True)
        return mapped


class ApiIntegrationConnector(BaseConnector):
    """Collects through a configured entry in API Management."""

    key = "api_integration"
    label = "Configured API integration"
    required_config = ("api_id",)

    def _api(self) -> ApiIntegration:
        api = self.db.get(ApiIntegration, self.config.get("api_id"))
        if api is None:
            raise ConnectorError("The linked API integration no longer exists")
        if api.status != "active":
            raise ConnectorError(
                f"API integration '{api.name}' is {api.status}; activate it after a successful test"
            )
        return api

    def fetch(self, *, criteria: dict[str, Any] | None = None, limit: int = 100) -> ConnectorReport:
        api = self._api()
        credentials = decrypt_json(api.credentials_encrypted)
        report = ConnectorReport()
        pages = max(1, int(api.max_pages or 1))
        for page in range(1, pages + 1):
            payload, _, _ = api_sync.perform_request(api, credentials, page=page, client=self.client)
            records = api_sync.extract_records(api, payload)
            report.pages += 1
            if not records:
                break
            for record in records:
                if len(report.listings) >= limit:
                    break
                mapped = api_sync.apply_mapping(api, record)
                if mapped:
                    report.listings.append(mapped)
            if api.pagination_type == "none":
                break
        report.notes.append(f"{len(report.listings)} record(s) mapped through API '{api.name}'")
        return report
