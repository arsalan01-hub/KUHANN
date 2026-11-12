"""Authentication, session and 2FA tests."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient

from app.models.user import User


def test_login_success_and_me(client: TestClient, admin_user):
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "TestPassw0rd!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "admin@test.local"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    # A super administrator holds the wildcard permission.
    assert me.json()["permission_codes"] == ["*"]
    assert me.json()["is_superuser"] is True


def test_login_rejects_wrong_password(client: TestClient, admin_user):
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_unknown_email(client: TestClient, admin_user):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@test.local", "password": "TestPassw0rd!"}
    )
    assert response.status_code == 401


def test_failed_attempts_lock_account(client: TestClient, db, admin_user):
    for _ in range(5):
        client.post(
            "/api/auth/login", json={"email": "admin@test.local", "password": "bad-password"}
        )
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "TestPassw0rd!"}
    )
    assert response.status_code == 423
    db.refresh(admin_user)
    assert admin_user.locked_until is not None


def test_requires_token(client: TestClient, admin_user):
    response = client.get("/api/dashboard")
    assert response.status_code == 401


def test_logout_revokes_token(client: TestClient, admin_headers):
    assert client.get("/api/dashboard", headers=admin_headers).status_code == 200
    assert client.post("/api/auth/logout", headers=admin_headers).status_code == 200
    assert client.get("/api/dashboard", headers=admin_headers).status_code == 401


def test_password_change_requires_current_password(client: TestClient, admin_headers):
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "wrong", "new_password": "AnotherPassw0rd!"},
    )
    assert response.status_code == 400


def test_password_change_rejects_weak_password(client: TestClient, admin_headers):
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "TestPassw0rd!", "new_password": "short"},
    )
    assert response.status_code == 422


def test_password_change_rotates_token(client: TestClient, admin_headers, admin_user):
    response = client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "TestPassw0rd!", "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 200
    # The old token was issued with the previous token_version.
    assert client.get("/api/dashboard", headers=admin_headers).status_code == 401
    new_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/dashboard", headers=new_headers).status_code == 200


def test_two_factor_enrollment_and_login(client: TestClient, db, admin_user):
    login = client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "TestPassw0rd!"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    setup = client.post("/api/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    enable = client.post("/api/auth/2fa/enable", headers=headers, json={"code": pyotp.TOTP(secret).now()})
    assert enable.status_code == 200

    # Password alone is no longer sufficient.
    missing = client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "TestPassw0rd!"}
    )
    assert missing.status_code == 401
    assert missing.json()["detail"] == "totp_required"

    invalid = client.post(
        "/api/auth/login",
        json={"email": "admin@test.local", "password": "TestPassw0rd!", "totp_code": "000000"},
    )
    assert invalid.status_code == 401

    valid = client.post(
        "/api/auth/login",
        json={
            "email": "admin@test.local",
            "password": "TestPassw0rd!",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert valid.status_code == 200


def test_disabled_account_cannot_login(client: TestClient, db, admin_user):
    admin_user.is_active = False
    db.commit()
    response = client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "TestPassw0rd!"}
    )
    assert response.status_code == 403


def test_login_is_audited(client: TestClient, db, admin_user):
    from app.models.system import AuditLog

    client.post("/api/auth/login", json={"email": "admin@test.local", "password": "wrong"})
    entry = db.query(AuditLog).filter(AuditLog.action == "auth.login").first()
    assert entry is not None
    assert entry.outcome == "failure"


def test_user_created_by_admin_can_sign_in(client: TestClient, admin_headers, db):
    response = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "email": "new.employee@test.local",
            "full_name": "New Employee",
            "password": "NewEmployee1!",
            "roles": ["employee"],
        },
    )
    assert response.status_code == 201
    user = db.query(User).filter(User.email == "new.employee@test.local").one()
    assert user.is_active
    login = client.post(
        "/api/auth/login",
        json={"email": "new.employee@test.local", "password": "NewEmployee1!"},
    )
    assert login.status_code == 200
