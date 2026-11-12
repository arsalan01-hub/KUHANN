"""Connectors, the collection pipeline, background jobs and saved-search monitoring."""

from __future__ import annotations

import httpx
import pytest

from app.connectors.base import ConnectorError
from app.models.listing import Listing
from app.models.search import SavedSearch
from app.models.source import WebsiteSource
from app.models.system import JobRun, Notification
from app.services import collector, jobs, notifications
from app.services.settings_service import get_setting


FEED = {
    "items": [
        {
            "id": "feed-1",
            "make": "Volvo",
            "model": "FH 460",
            "year": 2019,
            "price": 39900,
            "currency": "EUR",
            "km": 550000,
            "url": "https://feed-trucks.example/1",
            "image": "https://feed-trucks.example/1.jpg",
            "country": "LT",
        },
        {
            "id": "feed-2",
            "make": "MAN",
            "model": "TGX 18.500",
            "year": 2021,
            "price": 62000,
            "currency": "EUR",
            "km": 310000,
            "url": "https://feed-trucks.example/2",
            "country": "DE",
        },
    ]
}

FEED_CONFIG = {
    "feed_url": "https://feed-trucks.example/feed.json",
    "records_path": "items",
    "field_map": {
        "external_id": "id",
        "manufacturer": "make",
        "model": "model",
        "year": "year",
        "price": "price",
        "currency": "currency",
        "mileage_km": "km",
        "original_url": "url",
        "primary_image_url": "image",
        "country": "country",
    },
}


def test_json_feed_connector_parses_records(db, seeded, source_factory, mock_http):
    mock_http["register"]("feed-trucks.example/feed.json", httpx.Response(200, json=FEED))
    source = source_factory(connector_config=FEED_CONFIG)
    from app.connectors import get_connector

    connector = get_connector(db, source)
    report = connector.fetch(limit=10)
    assert len(report.listings) == 2
    assert report.listings[0]["manufacturer"] == "Volvo"
    assert report.listings[1]["model"] == "TGX 18.500"


def test_html_connector_refuses_when_robots_disallow(db, seeded, source_factory):
    source = source_factory(
        connector_key="html_listing",
        access_method="html",
        robots_allows_crawl=False,
        connector_config={
            "listing_url": "https://blocked.example/trucks",
            "item_selector": ".card",
            "fields": {"manufacturer": ".make"},
        },
    )
    from app.connectors import get_connector

    with pytest.raises(ConnectorError):
        get_connector(db, source).fetch()


def test_html_connector_extracts_configured_selectors(db, seeded, source_factory, mock_http):
    html = """
    <html><body>
      <div class="card"><span class="make">Iveco</span><span class="model">Stralis</span>
        <span class="price">€ 21 500</span><a href="/truck/1">open</a></div>
      <div class="card"><span class="make">Renault</span><span class="model">T 460</span>
        <span class="price">€ 33 000</span><a href="/truck/2">open</a></div>
    </body></html>
    """
    mock_http["register"]("dealer.example/stock", httpx.Response(200, text=html))
    source = source_factory(
        connector_key="html_listing",
        access_method="html",
        robots_allows_crawl=True,
        connector_config={
            "listing_url": "https://dealer.example/stock",
            "item_selector": ".card",
            "link_selector": "a",
            "fields": {
                "manufacturer": ".make",
                "model": ".model",
                "price": ".price",
            },
        },
    )
    from app.connectors import get_connector

    report = get_connector(db, source).fetch()
    assert len(report.listings) == 2
    assert report.listings[0]["manufacturer"] == "Iveco"
    assert report.listings[0]["original_url"] == "https://dealer.example/truck/1"


def test_collection_pipeline_creates_listings(db, seeded, source_factory, mock_http):
    mock_http["register"]("feed-trucks.example/feed.json", httpx.Response(200, json=FEED))
    source = source_factory(connector_config=FEED_CONFIG)
    summary = collector.collect_source(db, source)
    assert summary["created"] == 2
    assert summary["updated"] == 0
    db.refresh(source)
    assert source.status == "active"
    assert source.last_run_status == "success"
    assert source.listings_collected == 2
    assert db.query(Listing).count() == 2


def test_collection_refuses_unapproved_source(db, seeded, source_factory, mock_http):
    source = source_factory(status="needs_review", connector_config=FEED_CONFIG)
    with pytest.raises(ConnectorError):
        collector.collect_source(db, source)


def test_collection_failure_recorded_and_notifies_admins(
    db, seeded, source_factory, mock_http, admin_user
):
    mock_http["register"]("feed-trucks.example/feed.json", httpx.Response(500, text="boom"))
    source = source_factory(connector_config=FEED_CONFIG)
    for _ in range(3):
        with pytest.raises(ConnectorError):
            collector.collect_source(db, source)
    db.refresh(source)
    assert source.last_run_status == "failed"
    assert source.consecutive_failures >= 3
    assert db.query(Notification).count() >= 1


def test_collect_all_job_summarises_results(db, seeded, source_factory, mock_http):
    mock_http["register"]("feed-trucks.example/feed.json", httpx.Response(200, json=FEED))
    source_factory(connector_config=FEED_CONFIG)
    run = jobs.run_job(db, "collect_all", trigger="manual")
    assert run.status == "success"
    assert "2 new listing" in run.message
    assert run.duration_ms is not None


def test_unknown_job_type_is_recorded_as_failure(db, seeded):
    run = jobs.run_job(db, "does_not_exist")
    assert run.status == "failed"
    assert "Unknown job type" in run.message


def test_discovery_job_uses_curated_provider_when_api_missing(db, seeded, mock_http):
    run = jobs.run_job(db, "discover_websites", config={"queries": ["poland trucks"], "limit": 2})
    assert run.status == "success"
    assert run.detail["provider"] == "curated_directory"
    assert db.query(WebsiteSource).count() >= 1


def test_saved_search_monitoring_creates_notification(db, seeded, source_factory, admin_user):
    source = source_factory()
    from app.services import listing_service
    from datetime import datetime, timedelta, timezone

    saved = SavedSearch(
        user_id=admin_user.id,
        name="Actros under 30k",
        filters={"manufacturer": "Mercedes-Benz", "price_max": 30000},
        source_ids=[],
        schedule="daily",
        notify=True,
        last_run_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(saved)
    db.commit()

    listing_service.upsert_listing(
        db,
        source,
        {
            "external_id": "saved-1",
            "manufacturer": "Mercedes-Benz",
            "model": "Actros 1845",
            "year": 2017,
            "price": 28000,
            "currency": "EUR",
            "original_url": "https://trucks.example/saved-1",
        },
    )
    db.commit()

    result = notifications.run_saved_search(db, saved)
    db.commit()
    assert result["matches"] == 1
    db.refresh(saved)
    assert saved.last_match_count == 1
    assert saved.total_matches == 1
    note = db.query(Notification).filter(Notification.category == "saved_search").first()
    assert note is not None
    assert note.user_id == admin_user.id
    assert "Actros under 30k" in note.title


def test_saved_search_endpoints(client, admin_headers, db, seeded):
    created = client.post(
        "/api/saved-searches",
        headers=admin_headers,
        json={
            "name": "Volvo FH",
            "filters": {"manufacturer": "Volvo"},
            "schedule": "daily",
            "notify": True,
        },
    )
    assert created.status_code == 201
    saved_id = created.json()["id"]

    listed = client.get("/api/saved-searches", headers=admin_headers).json()
    assert len(listed["items"]) == 1

    run = client.post(f"/api/saved-searches/{saved_id}/run", headers=admin_headers)
    assert run.status_code == 200
    assert "matches" in run.json()

    patched = client.patch(
        f"/api/saved-searches/{saved_id}", headers=admin_headers, json={"is_active": False}
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    assert client.delete(f"/api/saved-searches/{saved_id}", headers=admin_headers).status_code == 200


def test_schedule_tick_runs_due_jobs(db, seeded, mock_http):
    from app.models.system import JobSchedule
    from datetime import datetime, timedelta, timezone

    schedule = db.query(JobSchedule).first()
    schedule.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    schedule.job_type = "run_saved_searches"
    db.commit()

    executed = jobs.tick(db, limit=1)
    assert len(executed) == 1
    db.refresh(schedule)
    assert schedule.last_status in ("success", "failed")
    assert schedule.next_run_at > datetime.now(timezone.utc) - timedelta(seconds=1)


def test_saved_search_filters_are_stored(db, seeded, admin_user):
    saved = SavedSearch(
        user_id=admin_user.id,
        name="Stored",
        filters={"country": ["LT", "LV"], "year_min": 2018},
        source_ids=["abc"],
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    assert saved.filters["country"] == ["LT", "LV"]
    assert saved.source_ids == ["abc"]
