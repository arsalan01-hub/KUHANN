"""Idempotent bootstrap: permissions, roles, administrator, schedules, catalogue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import session_scope
from app.models.source import WebsiteSource
from app.models.system import JobSchedule
from app.models.user import Permission, Role, User
from app.services.curated_sources import CURATED_SOURCES
from app.services.jobs import ensure_default_schedules
from app.services.settings_service import ensure_defaults

logger = logging.getLogger("kuhhan.bootstrap")

PERMISSIONS: dict[str, str] = {
    "dashboard:read": "View the operational dashboard",
    "listings:read": "View collected listings and truck details",
    "listings:write": "Review, flag and moderate listings",
    "search:read": "Run truck searches across approved sources",
    "saved_searches:write": "Create and manage saved searches",
    "sources:read": "View website sources and connector status",
    "sources:write": "Add, approve, configure and remove website sources",
    "discovery:run": "Run the website discovery engine",
    "apis:read": "View API integrations (credentials stay masked)",
    "apis:write": "Create, test, activate and delete API integrations",
    "users:read": "View user accounts",
    "users:write": "Create, edit, deactivate and unlock users",
    "roles:read": "View roles and permissions",
    "roles:write": "Create and modify roles",
    "audit:read": "Read the audit trail",
    "jobs:read": "View background jobs and schedules",
    "jobs:run": "Trigger background jobs and change schedules",
    "health:read": "View system health and monitoring",
    "backups:read": "List and download backup records",
    "backups:write": "Create and prune database backups",
    "settings:read": "View system settings",
    "settings:write": "Modify system settings",
    "notifications:read": "View notifications",
    "price:read": "View price analytics and history",
}

ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "super_admin": {
        "description": "Full control of the platform",
        "permissions": list(PERMISSIONS.keys()),
    },
    "admin": {
        "description": "Administrative access including sources, APIs and users",
        "permissions": [code for code in PERMISSIONS if code not in ("roles:write",)],
    },
    "manager": {
        "description": "Operational access: sources, collection and monitoring",
        "permissions": [
            "dashboard:read",
            "listings:read",
            "listings:write",
            "search:read",
            "saved_searches:write",
            "sources:read",
            "sources:write",
            "discovery:run",
            "apis:read",
            "jobs:read",
            "jobs:run",
            "audit:read",
            "health:read",
            "price:read",
            "notifications:read",
        ],
    },
    "employee": {
        "description": "Read-only research access",
        "permissions": [
            "dashboard:read",
            "listings:read",
            "search:read",
            "saved_searches:write",
            "sources:read",
            "price:read",
            "notifications:read",
        ],
    },
}


def ensure_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code, description in PERMISSIONS.items():
        if code not in existing:
            permission = Permission(code=code, description=description)
            db.add(permission)
            existing[code] = permission
    db.flush()
    return existing


def ensure_roles(db: Session) -> dict[str, Role]:
    permissions = ensure_permissions(db)
    roles = {r.name: r for r in db.scalars(select(Role)).all()}
    for name, definition in ROLE_DEFINITIONS.items():
        role = roles.get(name)
        if role is None:
            role = Role(name=name, description=definition["description"], is_system=True)
            db.add(role)
            roles[name] = role
        role.description = definition["description"]
        role.permissions = [permissions[code] for code in definition["permissions"]]
    db.flush()
    return roles


def ensure_admin(db: Session, roles: dict[str, Role]) -> User | None:
    email = settings.admin_email.strip().lower()
    if not email or not settings.admin_password:
        return None
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    user = User(
        email=email,
        full_name=settings.admin_name,
        password_hash=hash_password(settings.admin_password),
        is_active=True,
        is_superuser=True,
        roles=[roles["super_admin"]],
    )
    db.add(user)
    db.flush()
    logger.warning("Created bootstrap administrator %s — change its password immediately", email)
    return user


def seed_catalogue(db: Session) -> int:
    if not settings.seed_source_catalogue:
        return 0
    existing = {
        domain for (domain,) in db.execute(select(WebsiteSource.domain)).all()
    }
    now = datetime.now(timezone.utc)
    created = 0
    for entry in CURATED_SOURCES:
        if entry["domain"] in existing:
            continue
        db.add(
            WebsiteSource(
                domain=entry["domain"],
                name=entry["name"],
                homepage_url=f"https://{entry['domain']}/",
                country=entry["country"],
                language=entry["language"],
                category=entry["category"],
                status="newly_discovered",
                access_method="manual",
                discovery_provider="curated_directory",
                discovery_query="bundled catalogue",
                discovered_at=now,
                review_note=(
                    "Catalogue entry only. Inspect the site (robots.txt, terms, API availability) "
                    "and approve an access method before collection."
                ),
                robots_notes="",
                compatibility={},
                analysis_report={},
                truck_evidence={},
                connector_config={},
            )
        )
        created += 1
    db.flush()
    return created


def run_bootstrap() -> dict[str, Any]:
    with session_scope() as db:
        ensure_defaults(db)
        roles = ensure_roles(db)
        admin = ensure_admin(db, roles)
        ensure_default_schedules(db)
        seeded = seed_catalogue(db)
        summary = {
            "permissions": len(PERMISSIONS),
            "roles": len(roles),
            "admin": admin.email if admin else None,
            "catalogue_seeded": seeded,
            "schedules": int(db.scalar(select(func.count(JobSchedule.id))) or 0),
        }
    logger.info("Bootstrap complete: %s", summary)
    return summary
