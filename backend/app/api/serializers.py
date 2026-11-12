"""JSON serialisers — the only place that shapes API responses."""

from __future__ import annotations

from typing import Any

from app.models.api import ApiIntegration, ApiSyncLog
from app.models.listing import Listing
from app.models.search import SavedSearch, SearchHistory
from app.models.source import DiscoveryRun, WebsiteSource
from app.models.system import AuditLog, Backup, JobRun, JobSchedule, Notification
from app.models.user import Role, User


def _f(value: Any) -> float | None:
    return float(value) if value is not None else None


def listing_dict(listing: Listing, *, include_description: bool = True) -> dict[str, Any]:
    data = {
        "id": listing.id,
        "source_id": listing.source_id,
        "source_name": listing.source_name,
        "original_url": listing.original_url,
        "external_id": listing.external_id,
        "manufacturer": listing.manufacturer,
        "model": listing.model,
        "year": listing.year,
        "price": _f(listing.price),
        "currency": listing.currency,
        "price_eur": _f(listing.price_eur),
        "mileage_km": listing.mileage_km,
        "power_hp": listing.power_hp,
        "axle_config": listing.axle_config,
        "axles_count": listing.axles_count,
        "euro_class": listing.euro_class,
        "transmission": listing.transmission,
        "fuel_type": listing.fuel_type,
        "cab_type": listing.cab_type,
        "condition": listing.condition,
        "country": listing.country,
        "city": listing.city,
        "primary_image_url": listing.primary_image_url,
        "image_count": listing.image_count,
        "listing_status": listing.listing_status,
        "extraction_status": listing.extraction_status,
        "completeness_pct": listing.completeness_pct,
        "missing_fields": listing.missing_fields or [],
        "validation_warnings": listing.validation_warnings or [],
        "risk_score": listing.risk_score,
        "risk_reasons": listing.risk_reasons or [],
        "risk_reviewed": listing.risk_reviewed,
        "first_discovered_at": listing.first_discovered_at,
        "last_checked_at": listing.last_checked_at,
        "last_seen_at": listing.last_seen_at,
        "last_price_change_at": listing.last_price_change_at,
        "unavailable_since": listing.unavailable_since,
        "images": [img.url for img in sorted(listing.images, key=lambda i: i.position)],
        "title": " ".join(
            part for part in [listing.manufacturer, listing.model, str(listing.year or "")] if part
        ),
    }
    if include_description:
        data["description"] = listing.description
        data["raw_data"] = listing.raw_data or {}
    return data


def source_dict(source: WebsiteSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "domain": source.domain,
        "name": source.name,
        "homepage_url": source.homepage_url,
        "listing_url": source.listing_url,
        "country": source.country,
        "language": source.language,
        "category": source.category,
        "status": source.status,
        "access_method": source.access_method,
        "connector_key": source.connector_key,
        "connector_config": source.connector_config or {},
        "robots_url": source.robots_url,
        "robots_allows_crawl": source.robots_allows_crawl,
        "robots_notes": source.robots_notes,
        "terms_url": source.terms_url,
        "api_doc_url": source.api_doc_url,
        "has_official_api": source.has_official_api,
        "truck_evidence": source.truck_evidence or {},
        "compatibility": source.compatibility or {},
        "analysis_report": source.analysis_report or {},
        "discovery_provider": source.discovery_provider,
        "discovery_query": source.discovery_query,
        "discovered_at": source.discovered_at,
        "approved_at": source.approved_at,
        "review_note": source.review_note,
        "last_checked_at": source.last_checked_at,
        "last_collected_at": source.last_collected_at,
        "last_run_status": source.last_run_status,
        "last_error": source.last_error,
        "consecutive_failures": source.consecutive_failures,
        "listings_collected": source.listings_collected,
        "average_response_ms": source.average_response_ms,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def discovery_run_dict(run: DiscoveryRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "provider": run.provider,
        "query": run.query,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "results_found": run.results_found,
        "sources_created": run.sources_created,
        "duplicates_skipped": run.duplicates_skipped,
        "message": run.message,
        "provider_configured": run.provider_configured,
        "details": run.details or {},
        "created_at": run.created_at,
    }


def api_dict(api: ApiIntegration, *, masked_credentials: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": api.id,
        "name": api.name,
        "provider_name": api.provider_name,
        "purpose": api.purpose,
        "website_source_id": api.website_source_id,
        "base_url": api.base_url,
        "endpoint_path": api.endpoint_path,
        "api_version": api.api_version,
        "http_method": api.http_method,
        "auth_type": api.auth_type,
        "header_name": api.header_name,
        "custom_headers": api.custom_headers or {},
        "query_params": api.query_params or {},
        "body_template": api.body_template or {},
        "has_credentials": bool(api.credentials_encrypted),
        "credential_fields": masked_credentials or {},
        "pagination_type": api.pagination_type,
        "page_parameter": api.page_parameter,
        "page_size_parameter": api.page_size_parameter,
        "page_size": api.page_size,
        "max_pages": api.max_pages,
        "records_path": api.records_path,
        "rate_limit_per_minute": api.rate_limit_per_minute,
        "timeout_seconds": api.timeout_seconds,
        "response_format": api.response_format,
        "status": api.status,
        "doc_url": api.doc_url,
        "last_test_at": api.last_test_at,
        "last_test_status": api.last_test_status,
        "last_test_message": api.last_test_message,
        "last_success_at": api.last_success_at,
        "last_error": api.last_error,
        "last_response_snippet": api.last_response_snippet,
        "last_response_ms": api.last_response_ms,
        "requests_total": api.requests_total,
        "errors_total": api.errors_total,
        "records_synced": api.records_synced,
        "created_at": api.created_at,
        "updated_at": api.updated_at,
        "mappings": [
            {
                "id": m.id,
                "external_field": m.external_field,
                "kuhhan_field": m.kuhhan_field,
                "transform": m.transform,
                "required": m.required,
                "default_value": m.default_value,
            }
            for m in api.mappings
        ],
    }


def sync_log_dict(log: ApiSyncLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "api_id": log.api_id,
        "status": log.status,
        "started_at": log.started_at,
        "finished_at": log.finished_at,
        "records_fetched": log.records_fetched,
        "records_created": log.records_created,
        "records_updated": log.records_updated,
        "request_url": log.request_url,
        "error": log.error,
        "detail": log.detail or {},
    }


def user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "totp_enabled": user.totp_enabled,
        "last_login_at": user.last_login_at,
        "locked_until": user.locked_until,
        "failed_login_count": user.failed_login_count,
        "created_at": user.created_at,
        "roles": [
            {"id": r.id, "name": r.name, "description": r.description, "is_system": r.is_system}
            for r in user.roles
        ],
        "permission_codes": sorted(user.permission_codes),
    }


def role_dict(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permission_codes": role.permission_codes,
        "user_count": len(role.users) if role.users is not None else 0,
    }


def saved_search_dict(saved: SavedSearch) -> dict[str, Any]:
    return {
        "id": saved.id,
        "user_id": saved.user_id,
        "name": saved.name,
        "mode": saved.mode,
        "filters": saved.filters or {},
        "source_ids": saved.source_ids or [],
        "schedule": saved.schedule,
        "notify": saved.notify,
        "is_active": saved.is_active,
        "last_run_at": saved.last_run_at,
        "last_match_count": saved.last_match_count,
        "total_matches": saved.total_matches,
        "created_at": saved.created_at,
    }


def history_dict(entry: SearchHistory) -> dict[str, Any]:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "mode": entry.mode,
        "query_text": entry.query_text,
        "filters": entry.filters or {},
        "source_ids": entry.source_ids or [],
        "result_count": entry.result_count,
        "duration_ms": entry.duration_ms,
        "created_at": entry.created_at,
    }


def notification_dict(item: Notification) -> dict[str, Any]:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "title": item.title,
        "body": item.body,
        "level": item.level,
        "category": item.category,
        "link": item.link,
        "read_at": item.read_at,
        "payload": item.payload or {},
        "created_at": item.created_at,
    }


def job_schedule_dict(schedule: JobSchedule) -> dict[str, Any]:
    return {
        "id": schedule.id,
        "name": schedule.name,
        "job_type": schedule.job_type,
        "interval_seconds": schedule.interval_seconds,
        "enabled": schedule.enabled,
        "config": schedule.config or {},
        "last_run_at": schedule.last_run_at,
        "last_status": schedule.last_status,
        "last_message": schedule.last_message,
        "next_run_at": schedule.next_run_at,
    }


def job_run_dict(run: JobRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "job_type": run.job_type,
        "schedule_id": run.schedule_id,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": run.duration_ms,
        "trigger": run.trigger,
        "message": run.message,
        "detail": run.detail or {},
    }


def audit_dict(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "user_email": entry.user_email,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "outcome": entry.outcome,
        "detail": entry.detail or {},
        "created_at": entry.created_at,
    }


def backup_dict(record: Backup) -> dict[str, Any]:
    return {
        "id": record.id,
        "filename": record.filename,
        "method": record.method,
        "status": record.status,
        "size_bytes": record.size_bytes,
        "checksum_sha256": record.checksum_sha256,
        "table_count": record.table_count,
        "row_count": record.row_count,
        "message": record.message,
        "verified_at": record.verified_at,
        "created_at": record.created_at,
    }
