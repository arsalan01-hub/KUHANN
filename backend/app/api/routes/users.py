"""User, role and permission administration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Pagination, client_ip, get_current_user, require_permission
from app.api.serializers import role_dict, user_dict
from app.core.audit import record_audit
from app.core.security import hash_password, validate_password_strength
from app.db.session import get_db
from app.models.user import Permission, Role, User
from app.schemas.common import RoleCreate, RoleUpdate, UserCreate, UserUpdate

router = APIRouter(tags=["Users & roles"])


def _get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _get_role(db: Session, role_id: str) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.get("/users")
def list_users(
    q: str | None = None,
    is_active: bool | None = None,
    pagination: Pagination = Depends(),
    _: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    conditions = []
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    users = db.scalars(
        stmt.order_by(User.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    ).all()
    return {
        "items": [user_dict(u) for u in users],
        "total": int(total),
        "page": pagination.page,
        "page_size": pagination.page_size,
        "pages": (int(total) + pagination.page_size - 1) // pagination.page_size,
    }


@router.post("/users", status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
) -> dict:
    problems = validate_password_strength(payload.password)
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    roles = []
    for name in payload.roles or ["employee"]:
        role = db.scalar(select(Role).where(Role.name == name))
        if role is None:
            raise HTTPException(status_code=422, detail=f"Unknown role '{name}'")
        roles.append(role)
    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
        roles=roles,
    )
    db.add(user)
    record_audit(
        db,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        user=actor,
        ip_address=client_ip(request),
        detail={"email": email, "roles": [r.name for r in roles]},
    )
    db.commit()
    return user_dict(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        if not payload.is_active and user.id == actor.id:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
        user.is_active = payload.is_active
        if not payload.is_active:
            user.token_version += 1
    if payload.roles is not None:
        roles = []
        for name in payload.roles:
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                raise HTTPException(status_code=422, detail=f"Unknown role '{name}'")
            roles.append(role)
        if user.is_superuser and "super_admin" not in [r.name for r in roles]:
            remaining = db.scalar(
                select(func.count(User.id)).where(User.is_superuser.is_(True), User.id != user.id)
            )
            if not remaining:
                raise HTTPException(
                    status_code=400, detail="At least one super administrator must remain"
                )
        user.roles = roles
    if payload.password:
        problems = validate_password_strength(payload.password)
        if problems:
            raise HTTPException(status_code=422, detail="; ".join(problems))
        user.password_hash = hash_password(payload.password)
        user.token_version += 1
        user.failed_login_count = 0
        user.locked_until = None
    record_audit(
        db,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        user=actor,
        ip_address=client_ip(request),
        detail={"fields": [k for k, v in payload.model_dump().items() if v is not None]},
    )
    db.commit()
    return user_dict(user)


@router.post("/users/{user_id}/unlock")
def unlock_user(
    user_id: str,
    request: Request,
    actor: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    user.locked_until = None
    user.failed_login_count = 0
    record_audit(
        db, action="user.unlock", entity_type="user", entity_id=user.id, user=actor,
        ip_address=client_ip(request),
    )
    db.commit()
    return user_dict(user)


@router.delete("/users/{user_id}")
def deactivate_user(
    user_id: str,
    request: Request,
    actor: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
) -> dict:
    user = _get_user(db, user_id)
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = False
    user.token_version += 1
    record_audit(
        db, action="user.deactivate", entity_type="user", entity_id=user.id, user=actor,
        ip_address=client_ip(request),
    )
    db.commit()
    return {"message": "User deactivated"}


@router.get("/roles")
def list_roles(
    _: User = Depends(require_permission("roles:read", "users:read")),
    db: Session = Depends(get_db),
) -> dict:
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    return {"items": [role_dict(r) for r in roles]}


@router.get("/permissions")
def list_permissions(
    _: User = Depends(require_permission("roles:read", "users:read")),
    db: Session = Depends(get_db),
) -> dict:
    permissions = db.scalars(select(Permission).order_by(Permission.code)).all()
    return {
        "items": [
            {"id": p.id, "code": p.code, "description": p.description} for p in permissions
        ]
    }


@router.post("/roles", status_code=201)
def create_role(
    payload: RoleCreate,
    request: Request,
    actor: User = Depends(require_permission("roles:write")),
    db: Session = Depends(get_db),
) -> dict:
    if db.scalar(select(Role).where(Role.name == payload.name)):
        raise HTTPException(status_code=409, detail="A role with this name already exists")
    permissions = db.scalars(
        select(Permission).where(Permission.code.in_(payload.permissions))
    ).all()
    if len(permissions) != len(set(payload.permissions)):
        raise HTTPException(status_code=422, detail="Unknown permission code")
    role = Role(name=payload.name, description=payload.description, permissions=list(permissions))
    db.add(role)
    record_audit(
        db, action="role.create", entity_type="role", entity_id=role.id, user=actor,
        ip_address=client_ip(request), detail={"name": payload.name},
    )
    db.commit()
    return role_dict(role)


@router.patch("/roles/{role_id}")
def update_role(
    role_id: str,
    payload: RoleUpdate,
    request: Request,
    actor: User = Depends(require_permission("roles:write")),
    db: Session = Depends(get_db),
) -> dict:
    role = _get_role(db, role_id)
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        permissions = db.scalars(
            select(Permission).where(Permission.code.in_(payload.permissions))
        ).all()
        if len(permissions) != len(set(payload.permissions)):
            raise HTTPException(status_code=422, detail="Unknown permission code")
        role.permissions = list(permissions)
    record_audit(
        db, action="role.update", entity_type="role", entity_id=role.id, user=actor,
        ip_address=client_ip(request),
    )
    db.commit()
    return role_dict(role)


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: str,
    request: Request,
    actor: User = Depends(require_permission("roles:write")),
    db: Session = Depends(get_db),
) -> dict:
    role = _get_role(db, role_id)
    if role.is_system:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted")
    if role.users:
        raise HTTPException(status_code=400, detail="Remove this role from its users first")
    db.delete(role)
    record_audit(
        db, action="role.delete", entity_type="role", entity_id=role_id, user=actor,
        ip_address=client_ip(request),
    )
    db.commit()
    return {"message": "Role deleted"}


@router.get("/auth/permissions")
def my_permissions(user: User = Depends(get_current_user)) -> dict:
    return {"permission_codes": sorted(user.permission_codes), "is_superuser": user.is_superuser}
