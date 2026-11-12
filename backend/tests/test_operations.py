"""Backups, health, dashboard, settings and audit endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.system import AuditLog, Backup
from app.services import backup_service


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert "database" in body


def test_system_health_reports_database_and_worker(client, admin_headers):
    response = client.get("/api/system/health", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["database"]["ok"] is True
    assert body["database"]["table_count"] > 10
    assert body["worker"]["ok"] is False  # no worker heartbeat in tests
    assert "disk" in body


def test_system_health_requires_permission(client, employee_headers):
    assert client.get("/api/system/health", headers=employee_headers).status_code == 403


def test_dashboard_returns_live_aggregates(client, admin_headers, db, seeded, source_factory):
    from app.services import listing_service

    source = source_factory()
    listing_service.upsert_listing(
        db,
        source,
        {
            "external_id": "dash-1",
            "manufacturer": "Volvo",
            "model": "FH",
            "year": 2020,
            "price": 50000,
            "currency": "EUR",
            "original_url": "https://trucks.example/dash-1",
            "country": "SE",
        },
    )
    db.commit()

    body = client.get("/api/dashboard", headers=admin_headers).json()
    assert body["totals"]["listings_total"] == 1
    assert body["totals"]["sources_total"] == 1
    assert body["charts"]["listings_by_country"] == [{"country": "SE", "count": 1}]
    assert body["totals"]["average_price_eur"] == 50000.0


def test_backup_creates_verified_artefact(db, seeded, tmp_backup_dir, admin_headers, client):
    record = backup_service.create_backup(db)
    assert record.status == "verified"
    assert record.checksum_sha256
    assert record.size_bytes > 0
    path = tmp_backup_dir / record.filename
    assert path.exists()

    verification = backup_service.verify_backup(path)
    assert verification["ok"] is True
    assert verification["table_count"] > 5

    listing = client.get("/api/backups", headers=admin_headers).json()
    assert any(item["filename"] == record.filename for item in listing["items"])
    assert listing["recovery_steps"]


def test_backup_endpoint_and_verification(client, admin_headers, db, tmp_backup_dir):
    created = client.post("/api/backups", headers=admin_headers)
    assert created.status_code == 201
    backup_id = created.json()["id"]
    verified = client.post(f"/api/backups/{backup_id}/verify", headers=admin_headers)
    assert verified.status_code == 200
    assert verified.json()["verification"]["ok"] is True


def test_backup_prune_removes_old_records(db, seeded, tmp_backup_dir):
    record = backup_service.create_backup(db)
    record.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db.commit()
    removed = backup_service.prune_backups(db, retention_days=1)
    assert removed == 1
    assert db.query(Backup).count() == 0
    assert not (tmp_backup_dir / record.filename).exists()


def test_backup_refuses_to_overwrite(db, seeded, tmp_backup_dir):
    first = backup_service.create_backup(db)
    path = tmp_backup_dir / first.filename
    assert path.exists()
    # A second backup uses a different filename, so the first file stays intact.
    second = backup_service.create_backup(db)
    assert second.filename != first.filename
    assert path.exists()


def test_audit_trail_records_privileged_actions(client, admin_headers, db, seeded, mock_http):
    client.post("/api/jobs/run", headers=admin_headers, json={"job_type": "refresh_risk"})
    actions = [entry.action for entry in db.query(AuditLog).all()]
    assert "job.run" in actions


def test_audit_endpoint_filters(client, admin_headers, db, seeded):
    client.post("/api/jobs/run", headers=admin_headers, json={"job_type": "refresh_risk"})
    response = client.get("/api/audit?action=job.run", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


def test_settings_read_and_update(client, admin_headers, db, seeded):
    listing = client.get("/api/settings", headers=admin_headers)
    assert listing.status_code == 200
    keys = {item["key"] for item in listing.json()["items"]}
    assert "risk.flag_threshold" in keys

    updated = client.put(
        "/api/settings/risk.flag_threshold", headers=admin_headers, json={"value": 55}
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == 55

    rejected = client.put("/api/settings/unknown.key", headers=admin_headers, json={"value": 1})
    assert rejected.status_code == 404


def test_settings_update_requires_permission(client, employee_headers):
    assert (
        client.put(
            "/api/settings/risk.flag_threshold", headers=employee_headers, json={"value": 10}
        ).status_code
        == 403
    )


def test_job_endpoints(client, admin_headers, db, seeded, mock_http):
    types = client.get("/api/jobs/types", headers=admin_headers)
    assert types.status_code == 200
    assert {item["job_type"] for item in types.json()["items"]} >= {
        "discover_websites",
        "collect_all",
        "run_saved_searches",
        "database_backup",
    }

    run = client.post(
        "/api/jobs/run", headers=admin_headers, json={"job_type": "discover_websites", "config": {"limit": 1}}
    )
    assert run.status_code == 200
    assert run.json()["status"] == "success"

    runs = client.get("/api/jobs/runs", headers=admin_headers).json()
    assert runs["total"] >= 1

    schedules = client.get("/api/jobs/schedules", headers=admin_headers).json()["items"]
    assert schedules
    schedule_id = schedules[0]["id"]
    patched = client.patch(
        f"/api/jobs/schedules/{schedule_id}",
        headers=admin_headers,
        json={"interval_seconds": 7200},
    )
    assert patched.status_code == 200
    assert patched.json()["interval_seconds"] == 7200


def test_price_analytics(client, admin_headers, db, seeded, source_factory):
    from app.services import listing_service

    source = source_factory()
    for index, price in enumerate((30000, 40000, 50000)):
        listing_service.upsert_listing(
            db,
            source,
            {
                "external_id": f"price-{index}",
                "manufacturer": "Scania",
                "model": "R 450",
                "year": 2018 + index,
                "price": price,
                "currency": "EUR",
                "original_url": f"https://trucks.example/price-{index}",
                "country": "LT",
            },
        )
    db.commit()

    summary = client.get("/api/price/summary", headers=admin_headers).json()
    assert summary["sample_size"] == 3
    assert summary["average_price_eur"] == 40000.0
    assert summary["min_price_eur"] == 30000.0
    assert "not transaction prices" in summary["disclaimer"]

    by_manufacturer = client.get("/api/price/by/manufacturer", headers=admin_headers).json()
    assert by_manufacturer["items"][0]["key"] == "Scania"

    history = client.get("/api/price/history?days=30", headers=admin_headers).json()
    assert history["series"]


def test_notifications_endpoints(client, admin_headers, db, seeded, admin_user):
    from app.services.notifications import notify

    notify(db, user_id=admin_user.id, title="Test alert", body="Something happened")
    db.commit()

    listed = client.get("/api/notifications", headers=admin_headers).json()
    assert listed["total"] == 1
    notification_id = listed["items"][0]["id"]

    assert client.post(f"/api/notifications/{notification_id}/read", headers=admin_headers).status_code == 200
    assert client.get("/api/notifications?unread_only=true", headers=admin_headers).json()["total"] == 0
    assert client.post("/api/notifications/read-all", headers=admin_headers).status_code == 200
