"""API integration: request building, auth, mapping, testing and synchronisation."""

from __future__ import annotations

import httpx
import pytest

from app.models.api import ApiIntegration
from app.models.listing import Listing
from app.services import api_sync


def _create_api(client, headers, source_id, **overrides):
    payload = {
        "name": overrides.pop("name", "Fleet Data API"),
        "provider_name": "FleetData",
        "base_url": "https://api.fleetdata.example",
        "endpoint_path": "/v1/trucks",
        "http_method": "GET",
        "auth_type": "api_key",
        "header_name": "X-API-Key",
        "pagination_type": "page",
        "page_size": 2,
        "max_pages": 1,
        "records_path": "data.items",
        "website_source_id": source_id,
        "credentials": {"api_key": "valid-key"},
        "mappings": [
            {"external_field": "vehicle.make", "kuhhan_field": "manufacturer", "transform": "none"},
            {"external_field": "vehicle.model", "kuhhan_field": "model", "transform": "none"},
            {"external_field": "vehicle.production_year", "kuhhan_field": "year", "transform": "int"},
            {"external_field": "vehicle.price", "kuhhan_field": "price", "transform": "float"},
            {"external_field": "vehicle.currency", "kuhhan_field": "currency", "transform": "upper"},
            {"external_field": "vehicle.km", "kuhhan_field": "mileage_km", "transform": "int"},
            {"external_field": "vehicle.image_url", "kuhhan_field": "primary_image_url"},
            {"external_field": "links.self", "kuhhan_field": "original_url"},
            {"external_field": "id", "kuhhan_field": "external_id"},
            {"external_field": "vehicle.country", "kuhhan_field": "country"},
        ],
    }
    payload.update(overrides)
    return client.post("/api/apis", headers=headers, json=payload)


def _payload():
    return {
        "data": {
            "items": [
                {
                    "id": "fd-1",
                    "vehicle": {
                        "make": "Scania",
                        "model": "R 450",
                        "production_year": "2019",
                        "price": "48.500",
                        "currency": "eur",
                        "km": "512000",
                        "image_url": "https://cdn.fleetdata.example/1.jpg",
                        "country": "lt",
                    },
                    "links": {"self": "https://fleetdata.example/trucks/fd-1"},
                },
                {
                    "id": "fd-2",
                    "vehicle": {
                        "make": "DAF",
                        "model": "XF 480",
                        "production_year": 2020,
                        "price": 55000,
                        "currency": "EUR",
                        "km": 430000,
                        "country": "de",
                    },
                    "links": {"self": "https://fleetdata.example/trucks/fd-2"},
                },
            ]
        }
    }


def test_activation_requires_successful_test(client, admin_headers, source_factory, mock_http):
    source = source_factory()
    created = _create_api(client, admin_headers, source.id)
    assert created.status_code == 201
    api_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    activation = client.post(f"/api/apis/{api_id}/activate", headers=admin_headers)
    assert activation.status_code == 400
    assert "test" in activation.json()["detail"].lower()


def test_connection_test_and_activation(client, admin_headers, source_factory, mock_http):
    mock_http["register"]("api.fleetdata.example", httpx.Response(200, json=_payload()))
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]

    result = client.post(f"/api/apis/{api_id}/test", headers=admin_headers).json()
    assert result["ok"] is True
    assert result["record_count"] == 2
    assert result["mapping_sample"]["manufacturer"] == "Scania"
    assert result["mapping_sample"]["year"] == 2019
    assert result["mapping_sample"]["price"] == 48500.0
    assert result["mapping_sample"]["currency"] == "EUR"
    checks = {check["name"]: check["ok"] for check in result["checks"]}
    assert checks["connection"] and checks["authentication"] and checks["field_mapping"]

    activation = client.post(f"/api/apis/{api_id}/activate", headers=admin_headers)
    assert activation.status_code == 200
    assert activation.json()["status"] == "active"


def test_sync_creates_normalised_listings(client, admin_headers, source_factory, mock_http, db):
    mock_http["register"]("api.fleetdata.example", httpx.Response(200, json=_payload()))
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]
    client.post(f"/api/apis/{api_id}/test", headers=admin_headers)
    client.post(f"/api/apis/{api_id}/activate", headers=admin_headers)

    log = client.post(f"/api/apis/{api_id}/sync", headers=admin_headers, json={}).json()
    assert log["status"] == "success"
    assert log["records_created"] == 2

    listings = db.query(Listing).all()
    assert len(listings) == 2
    scania = next(item for item in listings if item.external_id == "fd-1")
    assert scania.manufacturer == "Scania"
    assert scania.year == 2019
    assert float(scania.price) == 48500
    assert scania.country == "LT"
    assert scania.source_id == source.id
    assert scania.original_url == "https://fleetdata.example/trucks/fd-1"
    assert scania.price_eur == pytest.approx(48500.0)


def test_invalid_credentials_are_reported(client, admin_headers, source_factory, mock_http, db):
    mock_http["register"](
        "api.fleetdata.example", httpx.Response(401, json={"error": "invalid api key"})
    )
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]

    result = client.post(f"/api/apis/{api_id}/test", headers=admin_headers).json()
    assert result["ok"] is False
    assert "401" in result["message"]
    stored = db.get(ApiIntegration, api_id)
    assert stored.last_test_status == "failed"
    assert stored.last_error

    activation = client.post(f"/api/apis/{api_id}/activate", headers=admin_headers)
    assert activation.status_code == 400


def test_malformed_response_is_reported(client, admin_headers, source_factory, mock_http):
    mock_http["register"](
        "api.fleetdata.example",
        httpx.Response(200, text="<html>not json</html>", headers={"content-type": "text/html"}),
    )
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]
    result = client.post(f"/api/apis/{api_id}/test", headers=admin_headers).json()
    assert result["ok"] is False
    assert "non-JSON" in result["message"]


def test_unreachable_host_is_reported(client, admin_headers, source_factory, mock_http):
    mock_http["register"]("api.fleetdata.example", httpx.Response(503, text="down"))
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]
    result = client.post(f"/api/apis/{api_id}/test", headers=admin_headers).json()
    assert result["ok"] is False
    assert "503" in result["message"]


def test_field_mapping_validation_rejects_unknown_target(client, admin_headers, source_factory):
    source = source_factory()
    response = _create_api(
        client,
        admin_headers,
        source.id,
        mappings=[{"external_field": "a", "kuhhan_field": "arbitrary_code", "transform": "none"}],
    )
    assert response.status_code == 422


def test_transform_helpers():
    assert api_sync.transform_value("1234", "int") == 1234
    assert api_sync.transform_value("12.5", "float") == 12.5
    assert api_sync.transform_value(" yes ", "bool") is True
    assert api_sync.transform_value("  abc ", "strip") == "abc"
    assert api_sync.transform_value("2019-05-01", "date") == "2019-05-01T00:00:00+00:00"
    with pytest.raises(api_sync.ApiConfigError):
        api_sync.transform_value("x", "eval")


def test_resolve_path_supports_arrays():
    payload = {"a": [{"b": {"c": 5}}, {"b": {"c": 6}}]}
    assert api_sync.resolve_path(payload, "a[1].b.c") == 6
    assert api_sync.resolve_path(payload, "a[5].b.c") is None
    assert api_sync.resolve_path(payload, "missing.path") is None


def test_credentials_update_keeps_existing_when_blank(client, admin_headers, source_factory, mock_http, db):
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]
    from app.core.crypto import decrypt_json

    client.patch(f"/api/apis/{api_id}", headers=admin_headers, json={"credentials": {"api_key": ""}})
    stored = db.get(ApiIntegration, api_id)
    assert decrypt_json(stored.credentials_encrypted)["api_key"] == "valid-key"

    client.patch(f"/api/apis/{api_id}", headers=admin_headers, json={"credentials": {"api_key": "rotated"}})
    db.refresh(stored)
    assert decrypt_json(stored.credentials_encrypted)["api_key"] == "rotated"


def test_sync_requires_active_integration(client, admin_headers, source_factory, mock_http):
    source = source_factory()
    api_id = _create_api(client, admin_headers, source.id).json()["id"]
    response = client.post(f"/api/apis/{api_id}/sync", headers=admin_headers, json={})
    assert response.status_code == 400
