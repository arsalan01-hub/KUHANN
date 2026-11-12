"""Role and permission administration."""

from __future__ import annotations

from app.models.user import Role, User


def test_bootstrap_creates_roles_and_permissions(db, seeded):
    names = {role.name for role in db.query(Role).all()}
    assert names == {"super_admin", "admin", "manager", "employee"}
    employee = db.query(Role).filter(Role.name == "employee").one()
    assert "search:read" in employee.permission_codes
    assert "sources:write" not in employee.permission_codes
    admin = db.query(Role).filter(Role.name == "admin").one()
    assert "sources:write" in admin.permission_codes
    assert "roles:write" not in admin.permission_codes


def test_roles_endpoint_lists_permissions(client, admin_headers):
    roles = client.get("/api/roles", headers=admin_headers).json()["items"]
    assert len(roles) == 4
    permissions = client.get("/api/permissions", headers=admin_headers).json()["items"]
    assert len(permissions) >= 20


def test_employee_cannot_read_roles(client, employee_headers):
    assert client.get("/api/roles", headers=employee_headers).status_code == 403


def test_admin_cannot_write_roles(client, admin_headers, db, seeded):
    from app.core.security import hash_password

    admin_role = db.query(Role).filter(Role.name == "admin").one()
    db.add(
        User(
            email="plain.admin@test.local",
            full_name="Plain Admin",
            password_hash=hash_password("PlainAdmin1!"),
            is_active=True,
            roles=[admin_role],
        )
    )
    db.commit()
    login = client.post(
        "/api/auth/login", json={"email": "plain.admin@test.local", "password": "PlainAdmin1!"}
    )
    assert login.status_code == 200
    plain_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    roles = client.get("/api/roles", headers=plain_headers).json()["items"]
    manager = next(role for role in roles if role["name"] == "manager")
    response = client.patch(
        f"/api/roles/{manager['id']}", headers=plain_headers, json={"permissions": ["search:read"]}
    )
    assert response.status_code == 403


def test_super_admin_can_create_and_update_role(client, admin_headers, db):
    created = client.post(
        "/api/roles",
        headers=admin_headers,
        json={"name": "logistics_coordinator", "description": "Coordinates loads", "permissions": ["search:read"]},
    )
    assert created.status_code == 201
    role_id = created.json()["id"]

    updated = client.patch(
        f"/api/roles/{role_id}",
        headers=admin_headers,
        json={"permissions": ["search:read", "listings:read", "saved_searches:write"]},
    )
    assert updated.status_code == 200
    assert set(updated.json()["permission_codes"]) == {
        "search:read",
        "listings:read",
        "saved_searches:write",
    }

    duplicate = client.post(
        "/api/roles", headers=admin_headers, json={"name": "logistics_coordinator", "permissions": []}
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        "/api/roles", headers=admin_headers, json={"name": "bad_role", "permissions": ["not:a:permission"]}
    )
    assert invalid.status_code == 422


def test_system_roles_cannot_be_deleted(client, admin_headers, db):
    roles = client.get("/api/roles", headers=admin_headers).json()["items"]
    employee = next(role for role in roles if role["name"] == "employee")
    assert client.delete(f"/api/roles/{employee['id']}", headers=admin_headers).status_code == 400


def test_admin_cannot_deactivate_self(client, admin_headers, admin_user):
    response = client.patch(
        f"/api/users/{admin_user.id}", headers=admin_headers, json={"is_active": False}
    )
    assert response.status_code == 400


def test_last_super_admin_cannot_lose_role(client, admin_headers, admin_user, db):
    response = client.patch(
        f"/api/users/{admin_user.id}", headers=admin_headers, json={"roles": ["employee"]}
    )
    assert response.status_code == 400
    db.refresh(admin_user)
    assert admin_user.has_permission("users:write")


def test_role_hierarchy_enforced_on_endpoint(client, admin_headers, db):
    created = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "email": "manager@test.local",
            "full_name": "Manager",
            "password": "ManagerPass1!",
            "roles": ["manager"],
        },
    )
    assert created.status_code == 201

    login = client.post(
        "/api/auth/login", json={"email": "manager@test.local", "password": "ManagerPass1!"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Manager may approve sources but not create users.
    assert client.post("/api/sources", headers=headers, json={"url": "https://x.example"}).status_code in (201, 422)
    assert client.get("/api/users", headers=headers).status_code == 403


def test_user_deactivation_revokes_sessions(client, admin_headers, db):
    client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "email": "temp@test.local",
            "full_name": "Temp",
            "password": "TempPass123!",
            "roles": ["employee"],
        },
    )
    login = client.post(
        "/api/auth/login", json={"email": "temp@test.local", "password": "TempPass123!"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    user = db.query(User).filter(User.email == "temp@test.local").one()
    assert client.delete(f"/api/users/{user.id}", headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_password_policy_on_user_creation(client, admin_headers):
    response = client.post(
        "/api/users",
        headers=admin_headers,
        json={"email": "weak@test.local", "password": "short", "roles": ["employee"]},
    )
    assert response.status_code == 422
