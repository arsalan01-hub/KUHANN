"""Shared pytest fixtures.

Tests run against a real PostgreSQL database (``kuhhan_test``) created next to
the configured application database — never SQLite. Every test starts from an
empty schema, so assertions describe what the code actually did.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models.user import Role, User
from app.services.bootstrap import ensure_permissions, ensure_roles
from app.services.jobs import ensure_default_schedules
from app.services.settings_service import ensure_defaults


def _test_database_url():
    url = make_url(settings.database_url)
    return url.set(database="kuhhan_test")


@pytest.fixture(scope="session")
def engine():
    admin_url = make_url(settings.database_url).set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'kuhhan_test'")
        ).scalar()
        if not exists:
            connection.execute(text("CREATE DATABASE kuhhan_test"))
    admin_engine.dispose()

    test_engine = create_engine(_test_database_url(), pool_pre_ping=True)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def SessionTesting(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture()
def db(engine, SessionTesting):
    with engine.begin() as connection:
        tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session: Session = SessionTesting()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded(db):
    ensure_defaults(db)
    roles = ensure_roles(db)
    ensure_default_schedules(db)
    db.commit()
    return roles


@pytest.fixture()
def admin_user(db, seeded):
    user = User(
        email="admin@test.local",
        full_name="Test Administrator",
        password_hash=hash_password("TestPassw0rd!"),
        is_active=True,
        is_superuser=True,
        roles=[db.query(Role).filter(Role.name == "super_admin").one()],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def employee_user(db, seeded):
    user = User(
        email="employee@test.local",
        full_name="Test Employee",
        password_hash=hash_password("EmployeePass1!"),
        is_active=True,
        roles=[db.query(Role).filter(Role.name == "employee").one()],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def client(db, SessionTesting):
    def override_get_db():
        session = SessionTesting()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client, admin_user):
    return auth_headers(client, "admin@test.local", "TestPassw0rd!")


@pytest.fixture()
def employee_headers(client, employee_user):
    return auth_headers(client, "employee@test.local", "EmployeePass1!")


@pytest.fixture()
def mock_http(monkeypatch):
    """Route every outbound request through an httpx mock transport."""

    routes: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url}"
        for pattern, response in routes.items():
            if pattern in key:
                return response
        return httpx.Response(404, text="not found", headers={"content-type": "text/plain"})

    def fresh_client() -> httpx.Client:
        # Production code closes the client it created, so hand out a new one per call.
        return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)

    monkeypatch.setattr("app.services.http.default_client", fresh_client)

    def register(pattern: str, response: httpx.Response) -> None:
        routes[pattern] = response

    return {"register": register, "client_factory": fresh_client}


@pytest.fixture()
def tmp_backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    return tmp_path / "backups"


@pytest.fixture()
def source_factory(db):
    from app.models.source import WebsiteSource

    def create(**overrides):
        domain = overrides.pop("domain", f"trucks-{uuid.uuid4().hex[:6]}.example")
        defaults = dict(
            domain=domain,
            name=overrides.pop("name", domain),
            homepage_url=f"https://{domain}/",
            country="LT",
            language="en",
            category="marketplace",
            status="approved",
            access_method="feed",
            connector_key="json_feed",
            connector_config={},
            robots_allows_crawl=True,
            compatibility={},
            analysis_report={},
            truck_evidence={},
            robots_notes="",
        )
        defaults.update(overrides)
        source = WebsiteSource(**defaults)
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    return create


@pytest.fixture(autouse=True)
def _quiet_logs(monkeypatch):
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
