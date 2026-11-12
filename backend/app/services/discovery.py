"""Autonomous website discovery engine.

Providers are pluggable. A provider that is not configured reports that fact —
the engine never fabricates discovered websites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json
from app.models.source import DiscoveryHit, DiscoveryRun, WebsiteSource
from app.services import inspector
from app.services.curated_sources import search_catalogue
from app.services.http import OutboundError, safe_request
from app.services.settings_service import get_setting, set_setting


@dataclass
class Candidate:
    domain: str
    url: str
    title: str = ""
    snippet: str = ""


class DiscoveryProvider(ABC):
    key: str
    label: str
    description: str

    @abstractmethod
    def is_configured(self, db: Session) -> tuple[bool, str]:
        """Return (configured, explanation)."""

    @abstractmethod
    def search(
        self, db: Session, query: str, limit: int, client: Any | None = None
    ) -> list[Candidate]:
        ...


class CuratedDirectoryProvider(DiscoveryProvider):
    key = "curated_directory"
    label = "Curated European directory"
    description = (
        "Bundled catalogue of publicly known European truck marketplaces, dealers and "
        "auctions. Always available; entries still require inspection and approval."
    )

    def is_configured(self, db: Session) -> tuple[bool, str]:
        return True, "Bundled catalogue is always available."

    def search(self, db: Session, query: str, limit: int, client: Any | None = None) -> list[Candidate]:
        return [
            Candidate(
                domain=entry["domain"],
                url=f"https://{entry['domain']}/",
                title=entry["name"],
                snippet=f"{entry['category']} · {entry['country']} · {entry['language']}",
            )
            for entry in search_catalogue(query, limit)
        ]


class SearchApiProvider(DiscoveryProvider):
    """Generic adapter for documented web-search APIs.

    Supported vendors: Brave Search, Google Programmable Search, Serper.
    The API key is stored encrypted in the system settings and never returned.
    """

    key = "search_api"
    label = "External search API"
    description = (
        "Queries a documented web-search API (Brave Search, Google Programmable Search or "
        "Serper) for truck-selling websites. Requires an API key."
    )

    def _config(self, db: Session) -> dict:
        cfg = dict(get_setting(db, "discovery.search_api", {}) or {})
        return cfg

    def is_configured(self, db: Session) -> tuple[bool, str]:
        cfg = self._config(db)
        if not cfg.get("enabled"):
            return False, "Search API provider is disabled in System Settings."
        if not cfg.get("endpoint"):
            return False, "No endpoint configured for the search API provider."
        credentials = decrypt_json(cfg.get("api_key_encrypted"))
        if not credentials.get("api_key"):
            return False, "No API key stored for the search API provider."
        if cfg.get("vendor") == "google_cse" and not cfg.get("cx"):
            return False, "Google Programmable Search requires a search engine id (cx)."
        return True, f"{cfg.get('vendor')} search API configured."

    def _headers_vendor(self, vendor: str, api_key: str) -> dict[str, str]:
        if vendor == "brave":
            return {"X-Subscription-Token": api_key, "Accept": "application/json"}
        if vendor == "serper":
            return {"X-API-KEY": api_key, "Content-Type": "application/json"}
        return {"Accept": "application/json"}

    def build_request(
        self, db: Session, query: str, limit: int
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        cfg = self._config(db)
        api_key = decrypt_json(cfg.get("api_key_encrypted")).get("api_key", "")
        vendor = cfg.get("vendor", "brave")
        endpoint = cfg.get("endpoint", "")
        params: dict[str, str] = {}
        if vendor == "brave":
            params = {"q": query, "count": str(min(limit, 20))}
        elif vendor == "google_cse":
            params = {"q": query, "key": api_key, "cx": cfg.get("cx", ""), "num": str(min(limit, 10))}
        elif vendor == "serper":
            params = {"q": query, "num": str(min(limit, 20))}
        else:
            params = {"q": query, "limit": str(limit), "api_key": api_key}
        return endpoint, self._headers_vendor(vendor, api_key), params

    @staticmethod
    def parse_results(vendor: str, payload: dict) -> list[Candidate]:
        results: list[Candidate] = []
        items: list[dict] = []
        if vendor == "brave":
            items = ((payload.get("web") or {}).get("results") or [])
        elif vendor == "google_cse":
            items = payload.get("items") or []
        elif vendor == "serper":
            items = payload.get("organic") or []
        else:
            items = payload.get("results") or payload.get("items") or []
        for item in items:
            url = item.get("link") or item.get("url") or ""
            if not url:
                continue
            try:
                domain = inspector.extract_domain(url)
            except ValueError:
                continue
            results.append(
                Candidate(
                    domain=domain,
                    url=url,
                    title=(item.get("title") or "")[:300],
                    snippet=(item.get("description") or item.get("snippet") or "")[:500],
                )
            )
        return results

    def search(self, db: Session, query: str, limit: int, client: Any | None = None) -> list[Candidate]:
        configured, reason = self.is_configured(db)
        if not configured:
            raise OutboundError(reason)
        endpoint, headers, params = self.build_request(db, query, limit)
        response = safe_request("GET", endpoint, client=client, headers=headers, params=params)
        if response.status_code >= 400:
            raise OutboundError(f"Search API returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OutboundError("Search API returned a non-JSON response") from exc
        vendor = self._config(db).get("vendor", "brave")
        return self.parse_results(vendor, payload)[:limit]


PROVIDERS: dict[str, DiscoveryProvider] = {
    CuratedDirectoryProvider.key: CuratedDirectoryProvider(),
    SearchApiProvider.key: SearchApiProvider(),
}


def provider_status(db: Session) -> list[dict]:
    out = []
    for provider in PROVIDERS.values():
        configured, reason = provider.is_configured(db)
        out.append(
            {
                "key": provider.key,
                "label": provider.label,
                "description": provider.description,
                "configured": configured,
                "status": reason,
            }
        )
    return out


def _create_source_from_candidate(
    db: Session, candidate: Candidate, provider_key: str, query: str, now: datetime
) -> WebsiteSource | None:
    existing = db.scalar(select(WebsiteSource).where(WebsiteSource.domain == candidate.domain))
    if existing is not None:
        return None
    source = WebsiteSource(
        domain=candidate.domain,
        name=candidate.title or candidate.domain,
        homepage_url=candidate.url,
        status="newly_discovered",
        access_method="manual",
        discovery_provider=provider_key,
        discovery_query=query[:300],
        discovered_at=now,
        robots_notes="",
        compatibility={},
        analysis_report={},
        connector_config={},
        truck_evidence={"discovery_snippet": candidate.snippet},
    )
    db.add(source)
    db.flush()
    return source


def run_discovery(
    db: Session,
    *,
    provider_key: str,
    query: str,
    limit: int = 20,
    user_id: str | None = None,
    client: Any | None = None,
    inspect_count: int | None = None,
) -> DiscoveryRun:
    now = datetime.now(timezone.utc)
    provider = PROVIDERS.get(provider_key)
    run = DiscoveryRun(
        provider=provider_key,
        query=query[:300],
        status="running",
        started_at=now,
        triggered_by=user_id,
        details={},
    )
    db.add(run)
    db.flush()

    if provider is None:
        run.status = "failed"
        run.message = f"Unknown discovery provider '{provider_key}'."
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return run

    configured, reason = provider.is_configured(db)
    run.provider_configured = configured
    if not configured:
        run.status = "unavailable"
        run.message = (
            "Provider is not configured, so no websites were searched. "
            f"{reason} Configure it under API Management → Discovery provider."
        )
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return run

    try:
        candidates = provider.search(db, query, limit, client=client)
    except OutboundError as exc:
        run.status = "failed"
        run.message = f"Discovery provider error: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        return run

    created: list[WebsiteSource] = []
    duplicates = 0
    for candidate in candidates:
        known = db.scalar(select(WebsiteSource).where(WebsiteSource.domain == candidate.domain))
        if known is None:
            source = _create_source_from_candidate(db, candidate, provider_key, query, now)
            if source is not None:
                created.append(source)
                known = source
        if known is None:
            duplicates += 1
            continue
        db.add(
            DiscoveryHit(
                run_id=run.id,
                domain=candidate.domain,
                url=candidate.url[:500],
                title=candidate.title[:300],
                snippet=candidate.snippet,
                provider=provider_key,
                already_known=not any(s.id == known.id for s in created),
            )
        )

    if inspect_count is None:
        inspect_count = int(get_setting(db, "discovery.max_inspect_per_run", 5) or 5)
    inspected = 0
    for source in created[:inspect_count]:
        try:
            report = inspector.inspect_website(source.homepage_url, client=client)
            analysis = inspector.build_analysis(report)
            source.name = analysis["name"][:200]
            source.country = analysis["country"] or source.country
            source.language = analysis["language"] or source.language
            source.listing_url = analysis["listing_url"]
            source.api_doc_url = analysis["api_doc_url"]
            source.terms_url = analysis["terms_url"]
            source.has_official_api = analysis["has_official_api"]
            source.robots_url = report.robots_url
            source.robots_allows_crawl = analysis["robots_allowed"]
            source.robots_notes = analysis["robots_notes"]
            source.status = analysis["status"]
            source.access_method = analysis["access_method"]
            source.compatibility = analysis["compatibility"]
            source.analysis_report = analysis["report"]
            source.truck_evidence = {
                "keyword_hits": report.truck_keyword_hits,
                "listing_candidates": report.listing_candidates,
                "description": report.description,
            }
            source.last_checked_at = datetime.now(timezone.utc)
            inspected += 1
        except Exception as exc:  # noqa: BLE001 - per-source isolation
            source.last_error = f"Inspection failed: {exc}"
            source.status = "temporarily_unavailable"

    run.results_found = len(candidates)
    run.sources_created = len(created)
    run.duplicates_skipped = duplicates
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.message = (
        f"{len(candidates)} candidate(s) returned by {provider.label}; "
        f"{len(created)} new website(s) registered, {inspected} inspected."
    )
    run.details = {
        "provider_label": provider.label,
        "inspected": inspected,
        "created_domains": [s.domain for s in created],
    }
    db.commit()
    return run


def configure_search_api(
    db: Session,
    *,
    enabled: bool,
    vendor: str,
    endpoint: str,
    api_key: str | None,
    cx: str = "",
) -> dict:
    cfg = dict(get_setting(db, "discovery.search_api", {}) or {})
    cfg.update({"enabled": enabled, "vendor": vendor, "endpoint": endpoint, "cx": cx})
    if api_key:
        cfg["api_key_encrypted"] = encrypt_json({"api_key": api_key})
    set_setting(db, "discovery.search_api", cfg)
    db.commit()
    return {**cfg, "api_key_encrypted": None, "has_api_key": bool(cfg.get("api_key_encrypted"))}
