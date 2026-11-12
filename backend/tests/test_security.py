"""Authorisation, injection, SSRF and secret-exposure tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.crypto import decrypt_json, encrypt_json
from app.services.http import OutboundError, safe_request, validate_outbound_url


def test_employee_cannot_write_sources(client: TestClient, employee_headers):
    response = client.post(
        "/api/sources", headers=employee_headers, json={"url": "https://example-trucks.example"}
    )
    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()


def test_employee_can_search_but_not_read_users(client: TestClient, employee_headers):
    assert client.post("/api/search", headers=employee_headers, json={"mode": "all_active"}).status_code == 200
    assert client.get("/api/users", headers=employee_headers).status_code == 403


def test_anonymous_cannot_read_any_protected_endpoint(client: TestClient):
    for path in ("/api/dashboard", "/api/listings", "/api/sources", "/api/apis", "/api/audit"):
        assert client.get(path).status_code == 401, path


def test_employee_cannot_escalate_by_patching_self(client: TestClient, employee_headers):
    response = client.patch(
        "/api/users/00000000-0000-0000-0000-000000000000",
        headers=employee_headers,
        json={"roles": ["super_admin"]},
    )
    assert response.status_code == 403


def test_invalid_token_is_rejected(client: TestClient):
    response = client.get("/api/dashboard", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8000/api",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.10/",
        "ftp://example.com/file",
        "http://example.com:22/",
        "http://user:password@example.com/",
    ],
)
def test_ssrf_guard_blocks_internal_targets(url):
    with pytest.raises(OutboundError):
        validate_outbound_url(url)


def test_ssrf_guard_allows_public_https():
    assert validate_outbound_url("https://example.com/api/v1") == "https://example.com/api/v1"


def test_api_credentials_are_encrypted_and_masked(
    client: TestClient, admin_headers, seeded, db, mock_http
):
    source_response = client.post(
        "/api/sources", headers=admin_headers, json={"url": "https://api-target.example"}
    )
    source_id = source_response.json()["id"]
    response = client.post(
        "/api/apis",
        headers=admin_headers,
        json={
            "name": "Secret API",
            "base_url": "https://api-target.example",
            "endpoint_path": "/v1/trucks",
            "auth_type": "api_key",
            "website_source_id": source_id,
            "credentials": {"api_key": "super-secret-key-value"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert "super-secret-key-value" not in str(body)
    assert body["has_credentials"] is True

    from app.models.api import ApiIntegration

    stored = db.query(ApiIntegration).filter(ApiIntegration.name == "Secret API").one()
    assert stored.credentials_encrypted
    assert "super-secret-key-value" not in stored.credentials_encrypted
    assert decrypt_json(stored.credentials_encrypted)["api_key"] == "super-secret-key-value"


def test_search_handles_sql_injection_attempt(client: TestClient, admin_headers):
    payload = {"mode": "all_active", "filters": {"q": "'; DROP TABLE listings; --"}}
    response = client.post("/api/search", headers=admin_headers, json=payload)
    assert response.status_code == 200
    assert response.json()["total"] == 0
    # Table still exists and serves requests.
    assert client.get("/api/listings", headers=admin_headers).status_code == 200


def test_invalid_source_url_is_rejected(client: TestClient, admin_headers):
    response = client.post("/api/sources", headers=admin_headers, json={"url": "javascript:alert(1)"})
    assert response.status_code == 422

    response = client.post("/api/sources", headers=admin_headers, json={"url": "https://"})
    assert response.status_code == 422


def test_encryption_roundtrip_and_redaction():
    token = encrypt_json({"api_key": "abcdef123456"})
    assert token and "abcdef123456" not in token
    assert decrypt_json(token)["api_key"] == "abcdef123456"
    assert decrypt_json("garbage") == {}


def test_security_headers_present(client: TestClient):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Cache-Control"] == "no-store"


def test_error_responses_do_not_leak_stack_traces(client: TestClient, admin_headers):
    response = client.get("/api/listings/does-not-exist", headers=admin_headers)
    assert response.status_code == 404
    assert "Traceback" not in response.text
