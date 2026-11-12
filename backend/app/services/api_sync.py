"""API integration plumbing: request building, auth, field mapping, sync.

Security notes
--------------
* Credentials are stored encrypted (see ``app.core.crypto``) and are only
  decrypted inside this module when a request is built.
* Field mapping is declarative (path + whitelisted transform). No expression
  evaluation, no dynamic imports, no shell access from the admin interface.
* All requests go through the SSRF guard in ``app.services.http``.
"""

from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.models.api import (
    KUHHAAN_FIELDS,
    TRANSFORMS,
    ApiIntegration,
    ApiSyncLog,
)
from app.services import listing_service, normalize
from app.services.http import OutboundError, safe_request
from app.services.settings_service import DEFAULTS

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class ApiConfigError(Exception):
    pass


def resolve_path(payload: Any, path: str | None) -> Any:
    """Resolve a dotted path with optional ``[index]`` segments."""
    if not path:
        return None
    current = payload
    for chunk in path.replace("[", ".[").split("."):
        if not chunk:
            continue
        if chunk.startswith("[") and chunk.endswith("]"):
            try:
                index = int(chunk[1:-1])
            except ValueError:
                return None
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict):
            if chunk not in current:
                return None
            current = current[chunk]
        else:
            return None
    return current


def transform_value(value: Any, transform: str) -> Any:
    if transform not in TRANSFORMS:
        raise ApiConfigError(f"Unsupported transform '{transform}'")
    if value is None:
        return None
    if transform == "none":
        return value
    if transform == "strip":
        return str(value).strip()
    if transform == "int":
        return normalize.parse_int(value)
    if transform == "float":
        return normalize.parse_float(value)
    if transform == "upper":
        return str(value).upper()
    if transform == "lower":
        return str(value).lower()
    if transform == "title":
        return str(value).title()
    if transform == "bool":
        text = str(value).strip().lower()
        return text in ("1", "true", "yes", "y", "ja")
    if transform == "date":
        parsed = normalize.parse_date(value)
        return parsed.isoformat() if parsed else None
    return value


def apply_mapping(api: ApiIntegration, record: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for mapping in api.mappings:
        if mapping.kuhhan_field not in KUHHAAN_FIELDS:
            raise ApiConfigError(f"Unknown KUHHAN field '{mapping.kuhhan_field}'")
        raw = resolve_path(record, mapping.external_field)
        if raw in (None, ""):
            raw = mapping.default_value
        value = transform_value(raw, mapping.transform)
        if value in (None, "") and mapping.required:
            raise ApiConfigError(
                f"Required field '{mapping.external_field}' is missing in the response"
            )
        if value not in (None, ""):
            mapped[mapping.kuhhan_field] = value
    return mapped


def _oauth_token(api: ApiIntegration, credentials: dict[str, Any], client) -> str:
    token_url = credentials.get("token_url")
    if not token_url:
        raise ApiConfigError("OAuth 2.0 requires a token URL")
    cached = _TOKEN_CACHE.get(api.id)
    if cached and cached[1] > time.time() + 30:
        return cached[0]
    payload = {
        "grant_type": "client_credentials",
        "client_id": credentials.get("client_id", ""),
        "client_secret": credentials.get("client_secret", ""),
        "scope": credentials.get("scope", ""),
    }
    response = safe_request("POST", token_url, client=client, params=payload)
    if response.status_code >= 400:
        raise ApiConfigError(f"OAuth token request failed with HTTP {response.status_code}")
    try:
        token = response.json().get("access_token")
    except ValueError as exc:
        raise ApiConfigError("OAuth token endpoint returned non-JSON") from exc
    if not token:
        raise ApiConfigError("OAuth token endpoint returned no access_token")
    expires_in = float(response.json().get("expires_in") or 3600)
    _TOKEN_CACHE[api.id] = (token, time.time() + expires_in)
    return token


def build_headers(
    api: ApiIntegration, credentials: dict[str, Any], client=None
) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    for key, value in (api.custom_headers or {}).items():
        headers[str(key)] = str(value)
    auth = api.auth_type
    if auth == "none":
        pass
    elif auth == "api_key":
        key = credentials.get("api_key")
        if not key:
            raise ApiConfigError("API key is not configured")
        headers[api.header_name or "X-API-Key"] = key
    elif auth == "bearer":
        token = credentials.get("token")
        if not token:
            raise ApiConfigError("Bearer token is not configured")
        headers["Authorization"] = f"Bearer {token}"
    elif auth == "basic":
        username = credentials.get("username") or ""
        password = credentials.get("password") or ""
        if not username:
            raise ApiConfigError("Basic authentication requires a username")
        raw = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {raw}"
    elif auth == "oauth2_client_credentials":
        token = _oauth_token(api, credentials, client)
        headers["Authorization"] = f"Bearer {token}"
    elif auth == "custom_headers":
        for key, value in (credentials.get("headers") or {}).items():
            headers[str(key)] = str(value)
    else:
        raise ApiConfigError(f"Unsupported authentication type '{auth}'")
    return headers


def build_url(api: ApiIntegration) -> str:
    base = (api.base_url or "").rstrip("/")
    path = (api.endpoint_path or "").strip()
    if not base.startswith(("http://", "https://")):
        raise ApiConfigError("Base URL must start with http:// or https://")
    if path and not path.startswith("/"):
        path = "/" + path
    return base + path


def build_request(
    api: ApiIntegration, credentials: dict[str, Any], *, page: int = 1, client=None
) -> dict[str, Any]:
    headers = build_headers(api, credentials, client)
    params: dict[str, Any] = {str(k): str(v) for k, v in (api.query_params or {}).items()}
    if api.pagination_type == "page":
        params[api.page_parameter or "page"] = str(page)
        params[api.page_size_parameter or "limit"] = str(api.page_size)
    elif api.pagination_type == "offset":
        params[api.page_parameter or "offset"] = str((page - 1) * api.page_size)
        params[api.page_size_parameter or "limit"] = str(api.page_size)
    body = None
    if api.http_method in ("POST", "PUT", "PATCH") and api.body_template:
        body = api.body_template
    return {
        "method": api.http_method,
        "url": build_url(api),
        "headers": headers,
        "params": params,
        "json_body": body,
        "timeout": float(api.timeout_seconds or 20),
    }


def extract_records(api: ApiIntegration, payload: Any) -> list[dict[str, Any]]:
    node = resolve_path(payload, api.records_path) if api.records_path else payload
    if isinstance(node, list):
        return [item for item in node if isinstance(item, dict)]
    if isinstance(node, dict):
        for key in ("results", "items", "data", "listings", "offers", "vehicles"):
            candidate = node.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return [node]
    return []


def perform_request(
    api: ApiIntegration, credentials: dict[str, Any], *, page: int = 1, client=None
) -> tuple[Any, dict[str, Any], float]:
    request = build_request(api, credentials, page=page, client=client)
    started = time.perf_counter()
    response = safe_request(
        request["method"],
        request["url"],
        client=client,
        headers=request["headers"],
        params=request["params"],
        json_body=request["json_body"],
        timeout=request["timeout"],
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if response.status_code >= 400:
        raise OutboundError(f"Upstream returned HTTP {response.status_code}")
    if api.response_format == "json":
        try:
            payload = response.json()
        except ValueError as exc:
            raise OutboundError("Upstream returned a non-JSON response") from exc
    else:
        payload = {"raw": response.text[:200_000]}
    return payload, request, elapsed_ms


def test_integration(api: ApiIntegration, *, client=None) -> dict[str, Any]:
    """Test connection, authentication, response structure and field mapping."""
    credentials = decrypt_json(api.credentials_encrypted)
    result: dict[str, Any] = {
        "ok": False,
        "auth_type": api.auth_type,
        "checks": [],
        "http_status": None,
        "latency_ms": None,
        "record_count": 0,
        "sample": None,
        "mapping_sample": None,
        "message": "",
    }
    now = datetime.now(timezone.utc)

    try:
        payload, request, elapsed_ms = perform_request(api, credentials, page=1, client=client)
        result["checks"].append({"name": "connection", "ok": True, "detail": "Endpoint reachable"})
        result["checks"].append(
            {"name": "authentication", "ok": True, "detail": f"{api.auth_type} accepted"}
        )
    except (OutboundError, ApiConfigError) as exc:
        api.last_test_at = now
        api.last_test_status = "failed"
        api.last_test_message = str(exc)
        api.last_error = str(exc)
        result["message"] = str(exc)
        result["checks"].append({"name": "connection", "ok": False, "detail": str(exc)})
        return result

    result["http_status"] = 200
    result["latency_ms"] = elapsed_ms
    result["request_url"] = request["url"]

    records = extract_records(api, payload)
    result["record_count"] = len(records)
    result["checks"].append(
        {
            "name": "response_structure",
            "ok": bool(records),
            "detail": f"{len(records)} record(s) found at '{api.records_path or '(root)'}'",
        }
    )
    if records:
        result["sample"] = {k: v for k, v in list(records[0].items())[:12]}
        try:
            mapped = apply_mapping(api, records[0])
            result["mapping_sample"] = mapped
            result["checks"].append(
                {
                    "name": "field_mapping",
                    "ok": bool(mapped),
                    "detail": f"{len(mapped)} of {len(api.mappings)} mapped field(s) resolved",
                }
            )
        except ApiConfigError as exc:
            result["checks"].append({"name": "field_mapping", "ok": False, "detail": str(exc)})
            result["message"] = str(exc)

    result["ok"] = all(check["ok"] for check in result["checks"])
    api.last_test_at = now
    api.last_test_status = "success" if result["ok"] else "failed"
    api.last_test_message = result["message"] or (
        "Connection, authentication and mapping validated" if result["ok"] else "Validation failed"
    )
    api.last_response_ms = elapsed_ms
    api.last_response_snippet = str(payload)[:2000]
    api.requests_total = (api.requests_total or 0) + 1
    if result["ok"]:
        api.last_success_at = now
        api.last_error = None
    else:
        api.errors_total = (api.errors_total or 0) + 1
        api.last_error = result["message"] or "Validation failed"
    return result


def sync_integration(
    db: Session,
    api: ApiIntegration,
    *,
    client=None,
    max_pages: int | None = None,
) -> ApiSyncLog:
    """Fetch pages, map records and upsert listings into the database."""
    from app.models.source import WebsiteSource

    log = ApiSyncLog(api_id=api.id, status="running", started_at=datetime.now(timezone.utc), detail={})
    db.add(log)
    db.flush()

    source = db.get(WebsiteSource, api.website_source_id) if api.website_source_id else None
    if source is None:
        log.status = "failed"
        log.error = "This API is not linked to a website source"
        log.finished_at = datetime.now(timezone.utc)
        api.last_error = log.error
        db.commit()
        return log

    credentials = decrypt_json(api.credentials_encrypted)
    pages = max_pages or max(1, int(api.max_pages or 1))
    created = updated = fetched = 0
    try:
        for page in range(1, pages + 1):
            payload, request, _ = perform_request(api, credentials, page=page, client=client)
            log.request_url = request["url"][:700]
            records = extract_records(api, payload)
            if not records:
                break
            fetched += len(records)
            for record in records:
                mapped = apply_mapping(api, record)
                if not mapped:
                    continue
                if not mapped.get("external_id"):
                    mapped["external_id"] = normalize.fingerprint(mapped)[:40]
                if not mapped.get("original_url"):
                    mapped["original_url"] = source.homepage_url
                listing, action = listing_service.upsert_listing(db, source, mapped)
                if action == "created":
                    created += 1
                else:
                    updated += 1
            if api.pagination_type == "none":
                break
        log.status = "success"
        log.records_fetched = fetched
        log.records_created = created
        log.records_updated = updated
        log.detail = {"pages": pages, "api": api.name}
        api.last_success_at = datetime.now(timezone.utc)
        api.last_error = None
        api.records_synced = (api.records_synced or 0) + created
        source.last_run_status = "success"
        source.last_collected_at = datetime.now(timezone.utc)
        source.listings_collected = (source.listings_collected or 0) + created
        source.consecutive_failures = 0
    except (OutboundError, ApiConfigError) as exc:
        log.status = "failed"
        log.error = str(exc)
        api.errors_total = (api.errors_total or 0) + 1
        api.last_error = str(exc)
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        source.last_run_status = "failed"
        source.last_error = str(exc)
    finally:
        log.finished_at = datetime.now(timezone.utc)
        db.commit()
    return log


__all__ = [
    "ApiConfigError",
    "apply_mapping",
    "build_request",
    "extract_records",
    "perform_request",
    "resolve_path",
    "sync_integration",
    "test_integration",
    "transform_value",
    "DEFAULTS",
]
