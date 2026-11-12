"""Search filters, listing ingestion, price history, risk and duplicates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.listing import Listing, PriceHistory
from app.services import listing_service, search_engine


def _truck(**overrides):
    data = {
        "external_id": "ext-1",
        "manufacturer": "Mercedes-Benz",
        "model": "Actros 1848",
        "year": 2018,
        "price": 29500,
        "currency": "EUR",
        "mileage_km": 620000,
        "power_hp": 480,
        "axle_config": "4x2",
        "euro_class": "Euro 6",
        "transmission": "Automatic",
        "fuel_type": "Diesel",
        "condition": "Used",
        "country": "LT",
        "city": "Vilnius",
        "description": "Well maintained truck with full service history.",
        "original_url": "https://trucks.example/listing/1",
        "primary_image_url": "https://trucks.example/img/1.jpg",
    }
    data.update(overrides)
    # Each fixture truck needs its own listing URL, otherwise the upsert treats
    # them as the same advertisement.
    if "original_url" not in overrides:
        data["original_url"] = f"https://trucks.example/listing/{data['external_id']}"
    if "primary_image_url" not in overrides:
        data["primary_image_url"] = f"https://trucks.example/img/{data['external_id']}.jpg"
    return data


def test_upsert_creates_and_updates_listing(db, seeded, source_factory):
    source = source_factory()
    listing, action = listing_service.upsert_listing(db, source, _truck())
    db.commit()
    assert action == "created"
    assert listing.completeness_pct >= 90
    assert listing.price_eur == 29500
    assert listing.first_discovered_at is not None

    listing, action = listing_service.upsert_listing(db, source, _truck(price=27500))
    db.commit()
    assert action == "price_changed"
    assert float(listing.price) == 27500
    assert listing.last_price_change_at is not None

    history = db.query(PriceHistory).filter(PriceHistory.listing_id == listing.id).all()
    assert len(history) == 2
    assert {float(entry.price) for entry in history} == {29500.0, 27500.0}


def test_currency_conversion_preserves_original(db, seeded, source_factory):
    source = source_factory()
    listing, _ = listing_service.upsert_listing(
        db, source, _truck(currency="PLN", price=120000, country="PL", external_id="pl-1")
    )
    db.commit()
    assert listing.currency == "PLN"
    assert float(listing.price) == 120000
    assert listing.price_eur is not None
    assert listing.price_eur < 120000


def test_search_filters_and_sorting(db, seeded, source_factory):
    source = source_factory()
    listing_service.upsert_listing(db, source, _truck(external_id="a", price=20000, year=2016))
    listing_service.upsert_listing(
        db, source, _truck(external_id="b", price=45000, year=2020, manufacturer="Volvo", model="FH 500")
    )
    listing_service.upsert_listing(
        db, source, _truck(external_id="c", price=31000, year=2019, country="PL", mileage_km=410000)
    )
    db.commit()

    everything = search_engine.run_search(db, filters={})
    assert everything.total == 3

    mercedes = search_engine.run_search(db, filters={"manufacturer": "Mercedes-Benz"})
    assert mercedes.total == 2

    cheap = search_engine.run_search(db, filters={"price_max": 30000})
    assert cheap.total == 1
    assert float(cheap.items[0].price) == 20000

    newer = search_engine.run_search(db, filters={"year_min": 2019})
    assert newer.total == 2

    low_mileage = search_engine.run_search(db, filters={"mileage_max": 500000})
    assert low_mileage.total == 1

    polish = search_engine.run_search(db, filters={"country": "PL"})
    assert polish.total == 1

    text = search_engine.run_search(db, filters={"q": "Actros"})
    assert text.total == 2

    by_price = search_engine.run_search(db, filters={}, sort="price_asc")
    assert [float(item.price) for item in by_price.items] == [20000.0, 31000.0, 45000.0]

    by_price_desc = search_engine.run_search(db, filters={}, sort="price_desc")
    assert float(by_price_desc.items[0].price) == 45000

    paged = search_engine.run_search(db, filters={}, page=2, page_size=2)
    assert paged.total == 3
    assert len(paged.items) == 1


def test_search_scoped_to_one_source(db, seeded, source_factory):
    first = source_factory(domain="first.example")
    second = source_factory(domain="second.example")
    listing_service.upsert_listing(db, first, _truck(external_id="1"))
    listing_service.upsert_listing(db, second, _truck(external_id="2"))
    db.commit()

    scoped = search_engine.run_search(db, filters={}, source_ids=[first.id])
    assert scoped.total == 1
    assert scoped.items[0].source_id == first.id
    assert scoped.source_status and scoped.source_status[0]["source_id"] == first.id


def test_missing_listings_marked_unreachable_not_sold(db, seeded, source_factory):
    source = source_factory()
    listing, _ = listing_service.upsert_listing(db, source, _truck())
    db.commit()
    marked = listing_service.mark_missing_listings(db, source, set())
    db.commit()
    assert marked == 0  # empty result set never mass-flags listings
    marked = listing_service.mark_missing_listings(db, source, {"some-other-id"})
    db.commit()
    db.refresh(listing)
    assert marked == 1
    assert listing.listing_status == "unreachable"
    assert listing.unavailable_since is not None


def test_duplicate_detection_across_sources(db, seeded, source_factory):
    first = source_factory(domain="one.example")
    second = source_factory(domain="two.example")
    listing_service.upsert_listing(
        db,
        first,
        _truck(external_id="a", original_url="https://one.example/1", primary_image_url="https://one.example/1.jpg"),
    )
    listing_service.upsert_listing(
        db,
        second,
        _truck(
            external_id="b",
            original_url="https://two.example/1",
            primary_image_url="https://two.example/1.jpg",
            price=29800,
        ),
    )
    db.commit()

    from app.models.listing import DuplicateCandidate

    candidates = db.query(DuplicateCandidate).all()
    assert len(candidates) == 1
    assert candidates[0].score >= 0.6
    assert candidates[0].status == "open"
    assert candidates[0].reasons


def test_risk_scoring_flags_implausible_listing(db, seeded, source_factory):
    source = source_factory()
    listing, _ = listing_service.upsert_listing(
        db,
        source,
        _truck(year=2035, price=0, mileage_km=9_000_000, description="x"),
    )
    db.commit()
    assert listing.risk_score >= 45
    assert listing.risk_reasons
    assert any("future" in reason.lower() for reason in listing.risk_reasons)


def test_low_price_outlier_flagged_against_cohort(db, seeded, source_factory):
    source = source_factory()
    for index in range(6):
        listing_service.upsert_listing(
            db,
            source,
            _truck(external_id=f"cohort-{index}", price=60000, original_url=f"https://trucks.example/{index}"),
        )
    cheap, _ = listing_service.upsert_listing(
        db, source, _truck(external_id="cheap", price=20000, original_url="https://trucks.example/cheap")
    )
    db.commit()
    assert cheap.risk_score >= 40
    assert any("below the model average" in reason for reason in cheap.risk_reasons)


def test_listing_endpoints_pagination_and_detail(client, admin_headers, db, seeded, source_factory):
    source = source_factory()
    listing, _ = listing_service.upsert_listing(db, source, _truck())
    db.commit()

    response = client.get("/api/listings?page_size=10", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1

    detail = client.get(f"/api/listings/{listing.id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["source"]["domain"] == source.domain
    assert detail.json()["price_history"]

    history = client.get(f"/api/listings/{listing.id}/price-history", headers=admin_headers)
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1


def test_save_and_favorite_listing(client, admin_headers, db, seeded, source_factory):
    source = source_factory()
    listing, _ = listing_service.upsert_listing(db, source, _truck())
    db.commit()

    assert client.post(f"/api/listings/{listing.id}/saved", headers=admin_headers, json={"kind": "saved"}).status_code == 200
    assert client.post(f"/api/listings/{listing.id}/saved", headers=admin_headers, json={"kind": "favorite"}).status_code == 200

    saved = client.get("/api/saved?kind=saved", headers=admin_headers).json()
    assert saved["total"] == 1
    favorites = client.get("/api/saved?kind=favorite", headers=admin_headers).json()
    assert favorites["total"] == 1

    saved_id = saved["items"][0]["saved_id"]
    assert client.delete(f"/api/saved/{saved_id}", headers=admin_headers).status_code == 200
    assert client.get("/api/saved?kind=saved", headers=admin_headers).json()["total"] == 0


def test_new_listings_window(db, seeded, source_factory):
    source = source_factory()
    listing, _ = listing_service.upsert_listing(db, source, _truck())
    listing.first_discovered_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()
    old = search_engine.run_search(db, filters={"added_since_days": 7})
    assert old.total == 0
    fresh = search_engine.run_search(db, filters={"added_since_days": 60})
    assert fresh.total == 1
