"""Website sources: manual addition, inspection, approval rules and discovery."""

from __future__ import annotations

import httpx
import pytest

from app.models.source import WebsiteSource
from app.services import discovery, inspector

HTML = """
<html lang="de"><head><title>LKW Trucks for sale</title>
<meta name="description" content="Used trucks, lorry and tractor unit listings">
</head><body>
<h1>Gebrauchte LKW kaufen</h1>
<a href="/fahrzeuge/listings">Alle Fahrzeuge</a>
<a href="/terms">Terms</a>
<a href="/api/docs">API</a>
</body></html>
"""


def _register_site(mock_http, domain: str, *, robots: str = "User-agent: *\nAllow: /\n"):
    # robots.txt is registered first so its more specific pattern wins.
    mock_http["register"](f"https://{domain}/robots.txt", httpx.Response(200, text=robots))
    mock_http["register"](
        f"https://{domain}", httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
    )


def test_add_website_creates_inspected_source(client, admin_headers, mock_http, db):
    _register_site(mock_http, "truck-shop.example")
    response = client.post(
        "/api/sources", headers=admin_headers, json={"url": "https://truck-shop.example/"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["domain"] == "truck-shop.example"
    assert body["status"] in ("needs_review", "under_investigation")
    assert body["robots_allows_crawl"] is True
    assert "trucks" in str(body["truck_evidence"]).lower()
    assert body["listing_url"]


def test_add_website_rejects_duplicate_domain(client, admin_headers, mock_http):
    _register_site(mock_http, "duplicate.example")
    first = client.post("/api/sources", headers=admin_headers, json={"url": "https://duplicate.example"})
    assert first.status_code == 201
    second = client.post("/api/sources", headers=admin_headers, json={"url": "https://duplicate.example/"})
    assert second.status_code == 409


def test_add_website_rejects_non_http_scheme(client, admin_headers):
    for url in ("ftp://example.com", "javascript:alert(1)", "not a url"):
        response = client.post("/api/sources", headers=admin_headers, json={"url": url})
        assert response.status_code == 422, url


def test_blocked_robots_prevents_approval(client, admin_headers, mock_http, db):
    _register_site(mock_http, "restricted.example", robots="User-agent: *\nDisallow: /\n")
    response = client.post(
        "/api/sources", headers=admin_headers, json={"url": "https://restricted.example"}
    )
    assert response.status_code == 201
    source_id = response.json()["id"]
    assert response.json()["status"] == "manual_access_only"
    assert response.json()["robots_allows_crawl"] is False

    approve = client.patch(
        f"/api/sources/{source_id}", headers=admin_headers, json={"status": "approved"}
    )
    assert approve.status_code == 422
    assert "robots.txt" in approve.json()["detail"]

    manual = client.patch(
        f"/api/sources/{source_id}",
        headers=admin_headers,
        json={"status": "manual_access_only"},
    )
    assert manual.status_code == 200


def test_approval_and_collection_permissions(client, employee_headers, source_factory):
    source = source_factory()
    assert client.patch(
        f"/api/sources/{source.id}", headers=employee_headers, json={"status": "approved"}
    ).status_code == 403


def test_discovery_without_configured_provider_does_not_invent_results(
    client, admin_headers, db
):
    response = client.post(
        "/api/discovery/run",
        headers=admin_headers,
        json={"provider": "search_api", "query": "used trucks", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["sources_created"] == 0
    assert "not configured" in body["message"].lower()
    assert db.query(WebsiteSource).count() == 0


def test_discovery_with_curated_catalogue_creates_sources(client, admin_headers, db, mock_http):
    # Catalogue entries are registered without network access; inspection failures
    # must not silently approve them.
    response = client.post(
        "/api/discovery/run",
        headers=admin_headers,
        json={"provider": "curated_directory", "query": "trucks", "limit": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["sources_created"] >= 1
    created = db.query(WebsiteSource).all()
    assert created
    for source in created:
        assert source.status != "approved"
        assert source.status != "active"


def test_search_api_config_requires_key(client, admin_headers, db):
    response = client.put(
        "/api/discovery/search-api",
        headers=admin_headers,
        json={"enabled": True, "vendor": "brave", "endpoint": "https://api.search.brave.com/res/v1/web/search"},
    )
    assert response.status_code == 200
    providers = client.get("/api/discovery/providers", headers=admin_headers).json()["items"]
    search_provider = next(item for item in providers if item["key"] == "search_api")
    assert search_provider["configured"] is False
    assert "API key" in search_provider["status"]


def test_search_api_provider_parses_results(client, admin_headers, db, mock_http):
    mock_http["register"](
        "api.search.brave.com",
        httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"link": "https://new-truck-site.example/", "title": "New Trucks"},
                        {"link": "https://second-site.example/listings", "title": "Second"},
                    ]
                }
            },
        ),
    )
    client.put(
        "/api/discovery/search-api",
        headers=admin_headers,
        json={
            "enabled": True,
            "vendor": "brave",
            "endpoint": "https://api.search.brave.com/res/v1/web/search",
            "api_key": "test-key",
        },
    )
    response = client.post(
        "/api/discovery/run",
        headers=admin_headers,
        json={"provider": "search_api", "query": "used trucks europe", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["results_found"] == 2
    assert body["sources_created"] == 2
    domains = {source.domain for source in db.query(WebsiteSource).all()}
    assert {"new-truck-site.example", "second-site.example"} <= domains


def test_inspector_detects_language_country_and_listing_pages(mock_http):
    _register_site(mock_http, "lkw-markt.example")
    report = inspector.inspect_website("https://lkw-markt.example")
    assert report.language == "de"
    assert report.truck_keyword_hits
    assert any("listings" in url for url in report.listing_candidates)
    assert report.terms_url


def test_inspector_reports_error_instead_of_faking_success(mock_http):
    mock_http["register"]("down.example", httpx.Response(503, text="unavailable"))
    report = inspector.inspect_website("https://down.example")
    assert report.error
    analysis = inspector.build_analysis(report)
    assert analysis["status"] == "temporarily_unavailable"
    assert analysis["access_method"] == "manual"
