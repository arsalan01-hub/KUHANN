"""API integration management: CRUD, credentials, testing, activation, sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, require_permission
from app.api.serializers import api_dict, sync_log_dict
from app.core.audit import record_audit
from app.core.crypto import decrypt_json, encrypt_json, redact
from app.db.session import get_db
from app.models.api import (
    AUTH_TYPES,
    HTTP_METHODS,
    KUHHAAN_FIELDS,
    PAGINATION_TYPES,
    TRANSFORMS,
    ApiFieldMapping,
    ApiIntegration,
    ApiSyncLog,
)
from app.models.source import WebsiteSource
from app.models.user import User
from app.services import api_sync
from app.services.http import OutboundError

router = APIRouter(prefix="/apis", tags=["API management"])

CREDENTIAL_FIELDS = ("api_key", "token", "username", "password", "client_id", "client_secret", "token_url", "scope", "headers")


def _api_or_404(db: Session, api_id: str) -> ApiIntegration:
    api = db.get(ApiIntegration, api_id)
    if api is None:
        raise HTTPException(status_code=404, detail="API integration not found")
    return api


def _validate_mappings(mappings: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for item in mappings:
        external = str(item.get("external_field") or "").strip()
        target = str(item.get("kuhhan_field") or "").strip()
        transform = str(item.get("transform") or "none")
        if not external or not target:
            raise HTTPException(status_code=422, detail="Each mapping needs a source and target field")
        if target not in KUHHAAN_FIELDS:
            raise HTTPException(status_code=422, detail=f"Unknown KUHHAN field '{target}'")
        if transform not in TRANSFORMS:
            raise HTTPException(status_code=422, detail=f"Unknown transform '{transform}'")
        cleaned.append(
            {
                "external_field": external[:200],
                "kuhhan_field": target,
                "transform": transform,
                "required": bool(item.get("required")),
                "default_value": (str(item.get("default_value"))[:200] if item.get("default_value") not in (None, "") else None),
            }
        )
    return cleaned


@router.get("/meta")
def api_meta(_: User = Depends(require_permission("apis:read"))) -> dict:
    return {
        "auth_types": list(AUTH_TYPES),
        "http_methods": list(HTTP_METHODS),
        "pagination_types": list(PAGINATION_TYPES),
        "kuhhan_fields": list(KUHHAAN_FIELDS),
        "transforms": list(TRANSFORMS),
    }


@router.get("")
def list_apis(
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("apis:read")),
    db: Session = Depends(get_db),
) -> dict:
    total = db.scalar(select(func.count(ApiIntegration.id))) or 0
    apis = db.scalars(
        select(ApiIntegration)
        .order_by(ApiIntegration.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [api_dict(a, masked_credentials=redact(decrypt_json(a.credentials_encrypted))) for a in apis],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.post("", status_code=201)
def create_api(
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="API name is required")
    if db.scalar(select(ApiIntegration).where(ApiIntegration.name == name)):
        raise HTTPException(status_code=409, detail="An API with this name already exists")
    auth_type = str(payload.get("auth_type") or "none")
    if auth_type not in AUTH_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported authentication type")
    method = str(payload.get("http_method") or "GET").upper()
    if method not in HTTP_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported HTTP method")
    pagination = str(payload.get("pagination_type") or "page")
    if pagination not in PAGINATION_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported pagination type")
    base_url = str(payload.get("base_url") or "").strip()
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="Base URL must start with http:// or https://")
    source_id = payload.get("website_source_id") or None
    if source_id and db.get(WebsiteSource, source_id) is None:
        raise HTTPException(status_code=422, detail="Linked website source not found")

    api = ApiIntegration(
        name=name,
        provider_name=str(payload.get("provider_name") or "")[:160],
        purpose=str(payload.get("purpose") or "listings")[:40],
        website_source_id=source_id,
        base_url=base_url[:500],
        endpoint_path=str(payload.get("endpoint_path") or "/")[:500],
        api_version=str(payload.get("api_version") or "")[:40],
        http_method=method,
        auth_type=auth_type,
        header_name=str(payload.get("header_name") or "X-API-Key")[:80],
        custom_headers=payload.get("custom_headers") or {},
        query_params=payload.get("query_params") or {},
        body_template=payload.get("body_template") or {},
        pagination_type=pagination,
        page_parameter=str(payload.get("page_parameter") or "page")[:60],
        page_size_parameter=str(payload.get("page_size_parameter") or "limit")[:60],
        page_size=int(payload.get("page_size") or 50),
        max_pages=int(payload.get("max_pages") or 5),
        records_path=str(payload.get("records_path") or "")[:200],
        rate_limit_per_minute=int(payload.get("rate_limit_per_minute") or 60),
        timeout_seconds=int(payload.get("timeout_seconds") or 20),
        response_format=str(payload.get("response_format") or "json")[:20],
        doc_url=payload.get("doc_url"),
        status="draft",
        created_by=user.id,
        credentials_encrypted=encrypt_json(payload.get("credentials") or {}),
    )
    db.add(api)
    db.flush()
    mappings = _validate_mappings(payload.get("mappings") or [])
    for mapping in mappings:
        db.add(ApiFieldMapping(api_id=api.id, **mapping))
    record_audit(
        db,
        action="api.create",
        entity_type="api_integration",
        entity_id=api.id,
        user=user,
        ip_address=client_ip(request),
        detail={"name": name, "auth_type": auth_type},
    )
    db.commit()
    db.refresh(api)
    return api_dict(api, masked_credentials=redact(decrypt_json(api.credentials_encrypted)))


@router.patch("/{api_id}")
def update_api(
    api_id: str,
    payload: dict,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    api = _api_or_404(db, api_id)
    simple_fields = (
        "name",
        "provider_name",
        "purpose",
        "base_url",
        "endpoint_path",
        "api_version",
        "header_name",
        "pagination_type",
        "page_parameter",
        "page_size_parameter",
        "records_path",
        "response_format",
        "doc_url",
    )
    for field in simple_fields:
        if payload.get(field) is not None:
            value = payload[field]
            if field == "base_url" and not str(value).startswith(("http://", "https://")):
                raise HTTPException(status_code=422, detail="Base URL must start with http:// or https://")
            setattr(api, field, value)
    if payload.get("http_method"):
        method = str(payload["http_method"]).upper()
        if method not in HTTP_METHODS:
            raise HTTPException(status_code=422, detail="Unsupported HTTP method")
        api.http_method = method
    if payload.get("auth_type"):
        if payload["auth_type"] not in AUTH_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported authentication type")
        api.auth_type = payload["auth_type"]
    if payload.get("pagination_type"):
        if payload["pagination_type"] not in PAGINATION_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported pagination type")
        api.pagination_type = payload["pagination_type"]
    for field in ("page_size", "max_pages", "rate_limit_per_minute", "timeout_seconds"):
        if payload.get(field) is not None:
            try:
                setattr(api, field, int(payload[field]))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=f"'{field}' must be a number") from exc
    for field in ("custom_headers", "query_params", "body_template"):
        if payload.get(field) is not None:
            if not isinstance(payload[field], dict):
                raise HTTPException(status_code=422, detail=f"'{field}' must be an object")
            setattr(api, field, payload[field])
    if payload.get("website_source_id") is not None:
        source_id = payload["website_source_id"] or None
        if source_id and db.get(WebsiteSource, source_id) is None:
            raise HTTPException(status_code=422, detail="Linked website source not found")
        api.website_source_id = source_id
    if payload.get("credentials"):
        merged = decrypt_json(api.credentials_encrypted)
        merged.update({k: v for k, v in payload["credentials"].items() if v not in (None, "")})
        api.credentials_encrypted = encrypt_json(merged)
        api.status = "draft" if api.status == "active" else api.status
    if payload.get("mappings") is not None:
        mappings = _validate_mappings(payload["mappings"])
        db.query(ApiFieldMapping).filter(ApiFieldMapping.api_id == api.id).delete(
            synchronize_session=False
        )
        for mapping in mappings:
            db.add(ApiFieldMapping(api_id=api.id, **mapping))
        api.status = "draft" if api.status == "active" else api.status
    record_audit(
        db, action="api.update", entity_type="api_integration", entity_id=api.id, user=user,
        ip_address=client_ip(request), detail={"fields": list(payload.keys())},
    )
    db.commit()
    db.refresh(api)
    return api_dict(api, masked_credentials=redact(decrypt_json(api.credentials_encrypted)))


@router.post("/{api_id}/test")
def test_api(
    api_id: str,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    api = _api_or_404(db, api_id)
    result = api_sync.test_integration(api)
    record_audit(
        db,
        action="api.test",
        entity_type="api_integration",
        entity_id=api.id,
        user=user,
        ip_address=client_ip(request),
        outcome="success" if result["ok"] else "failure",
        detail={"checks": result["checks"]},
    )
    db.commit()
    return result


@router.post("/{api_id}/activate")
def activate_api(
    api_id: str,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    api = _api_or_404(db, api_id)
    if api.last_test_status != "success":
        raise HTTPException(
            status_code=400,
            detail="Run a successful connection test before activating this integration",
        )
    if not api.website_source_id:
        raise HTTPException(
            status_code=400, detail="Link the API to a website source before activating it"
        )
    api.status = "active"
    record_audit(
        db, action="api.activate", entity_type="api_integration", entity_id=api.id, user=user,
        ip_address=client_ip(request),
    )
    db.commit()
    return api_dict(api, masked_credentials=redact(decrypt_json(api.credentials_encrypted)))


@router.post("/{api_id}/deactivate")
def deactivate_api(
    api_id: str,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    api = _api_or_404(db, api_id)
    api.status = "disabled"
    record_audit(
        db, action="api.deactivate", entity_type="api_integration", entity_id=api.id, user=user,
        ip_address=client_ip(request),
    )
    db.commit()
    return api_dict(api, masked_credentials=redact(decrypt_json(api.credentials_encrypted)))


@router.post("/{api_id}/sync")
def sync_api(
    api_id: str,
    payload: dict | None = None,
    request: Request = None,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    api = _api_or_404(db, api_id)
    if api.status != "active":
        raise HTTPException(status_code=400, detail="Activate the integration before syncing")
    max_pages = (payload or {}).get("max_pages")
    try:
        log = api_sync.sync_integration(db, api, max_pages=max_pages)
    except OutboundError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    record_audit(
        db,
        action="api.sync",
        entity_type="api_integration",
        entity_id=api.id,
        user=user,
        ip_address=client_ip(request) if request else None,
        outcome="success" if log.status == "success" else "failure",
        detail={"created": log.records_created, "updated": log.records_updated},
    )
    db.commit()
    return sync_log_dict(log)


@router.get("/{api_id}/logs")
def api_logs(
    api_id: str,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("apis:read")),
    db: Session = Depends(get_db),
) -> dict:
    _api_or_404(db, api_id)
    total = db.scalar(
        select(func.count(ApiSyncLog.id)).where(ApiSyncLog.api_id == api_id)
    ) or 0
    logs = db.scalars(
        select(ApiSyncLog)
        .where(ApiSyncLog.api_id == api_id)
        .order_by(ApiSyncLog.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return {
        "items": [sync_log_dict(log) for log in logs],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.delete("/{api_id}")
def delete_api(
    api_id: str,
    request: Request,
    user: User = Depends(require_permission("apis:write")),
    db: Session = Depends(get_db),
) -> dict:
    api = _api_or_404(db, api_id)
    name = api.name
    db.delete(api)
    record_audit(
        db, action="api.delete", entity_type="api_integration", entity_id=api_id, user=user,
        ip_address=client_ip(request), detail={"name": name},
    )
    db.commit()
    return {"message": "API integration deleted"}
