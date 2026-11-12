"""Unit tests for number, currency, date and text normalisation."""

from __future__ import annotations

from app.services import normalize


def test_price_parsing_handles_european_formats():
    assert normalize.parse_float("48.500") == 48500.0
    assert normalize.parse_float("48.500,00") == 48500.0
    assert normalize.parse_float("48,500.00") == 48500.0
    assert normalize.parse_float("€ 21 500") == 21500.0
    assert normalize.parse_float("12,5") == 12.5
    assert normalize.parse_float("48500.75") == 48500.75
    assert normalize.parse_float("") is None
    assert normalize.parse_float("on request") is None


def test_integer_parsing_and_currency_aliases():
    assert normalize.parse_int("512 000 km") == 512000
    assert normalize.parse_int("1.234.567") == 1234567
    assert normalize.normalise_currency("zł") == "PLN"
    assert normalize.normalise_currency("€") == "EUR"
    assert normalize.normalise_currency("usd") == "USD"
    assert normalize.normalise_currency(None) == "EUR"


def test_currency_conversion_to_eur():
    rates = {"EUR": 1.0, "PLN": 0.25}
    assert normalize.price_to_eur(40000, "PLN", rates) == 10000.0
    assert normalize.price_to_eur(40000, "EUR", rates) == 40000.0
    assert normalize.price_to_eur(None, "EUR", rates) is None


def test_manufacturer_and_axle_normalisation():
    assert normalize.normalise_manufacturer("mercedes benz") == "Mercedes-Benz"
    assert normalize.normalise_manufacturer("MAN") == "MAN"
    assert normalize.normalise_manufacturer("volvo") == "Volvo"
    assert normalize.normalise_axle_config("4 X 2 tractor") == "4x2"
    assert normalize.normalise_axle_config("6x4") == "6x4"


def test_date_parsing_variants():
    assert normalize.parse_date("2019-05-01").year == 2019
    assert normalize.parse_date("01.05.2019").month == 5
    assert normalize.parse_date("2019-05-01T10:00:00Z").hour == 10
    assert normalize.parse_date(1556700000).year == 2019
    assert normalize.parse_date("nonsense") is None


def test_completeness_and_validation():
    pct, missing = normalize.completeness(
        {
            "manufacturer": "Volvo",
            "model": "FH",
            "year": 2020,
            "price": 50000,
            "currency": "EUR",
            "mileage_km": 400000,
            "power_hp": 500,
            "country": "SE",
            "original_url": "https://x.example/1",
            "primary_image_url": "https://x.example/1.jpg",
            "axle_config": "4x2",
            "euro_class": "Euro 6",
        }
    )
    assert pct == 100
    assert missing == []

    pct, missing = normalize.completeness({"manufacturer": "Volvo"})
    assert pct == 14
    assert "model" in missing

    warnings = normalize.validate_listing(
        {"year": 2060, "price": 0, "mileage_km": 4_000_000, "original_url": "ftp://x"}
    )
    assert any("future" in warning for warning in warnings)
    assert any("zero" in warning.lower() for warning in warnings)
    assert any("mileage" in warning.lower() for warning in warnings)


def test_fingerprint_is_stable_and_distinct():
    base = {"manufacturer": "Volvo", "model": "FH", "year": 2020, "mileage_km": 400000, "price": 50000, "country": "SE"}
    assert normalize.fingerprint(base) == normalize.fingerprint(dict(base))
    changed = dict(base)
    changed["price"] = 51000
    assert normalize.fingerprint(base) != normalize.fingerprint(changed)
