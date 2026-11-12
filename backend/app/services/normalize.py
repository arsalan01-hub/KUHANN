"""Normalisation helpers: currency, integers, manufacturers, completeness."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

MANUFACTURER_ALIASES = {
    "mercedes benz": "Mercedes-Benz",
    "mercedesbenz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mb": "Mercedes-Benz",
    "actros": "Mercedes-Benz",
    "man": "MAN",
    "man tgx": "MAN",
    "daf": "DAF",
    "volvo": "Volvo",
    "scania": "Scania",
    "iveco": "Iveco",
    "renault": "Renault",
    "renault trucks": "Renault Trucks",
    "ford": "Ford",
    "isuzu": "Isuzu",
    "mitsubishi": "Mitsubishi",
    "fuso": "Fuso",
    "hino": "Hino",
    "kia": "Kia",
    "hyundai": "Hyundai",
    "tatra": "Tatra",
    "solaris": "Solaris",
    "setra": "Setra",
    "neoplan": "Neoplan",
}

CURRENCY_ALIASES = {
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "zł": "PLN",
    "zl": "PLN",
    "pln": "PLN",
    "usd": "USD",
    "$": "USD",
    "gbp": "GBP",
    "£": "GBP",
    "sek": "SEK",
    "nok": "NOK",
    "dkk": "DKK",
    "czk": "CZK",
    "huf": "HUF",
    "ron": "RON",
}

# Field weight (out of 100) used for the completeness score.
COMPLETENESS_WEIGHTS: dict[str, int] = {
    "manufacturer": 14,
    "model": 12,
    "year": 10,
    "price": 16,
    "currency": 4,
    "mileage_km": 10,
    "power_hp": 6,
    "country": 4,
    "original_url": 10,
    "primary_image_url": 8,
    "axle_config": 3,
    "euro_class": 3,
}
CRITICAL_FIELDS = ("manufacturer", "model", "year", "price", "original_url")


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = str(value)
    cleaned = re.sub(r"[^\d,.\-]", "", text).strip()
    if not cleaned or cleaned in {"-", ".", ","}:
        return None
    # Normalise thousands separators: 12.500,00 / 12,500.00 / 12 500 / 48.500
    if cleaned.count(",") and cleaned.count("."):
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1:
        whole, fraction = cleaned.split(",")
        # "12,500" on a European listing is a thousands separator; "12,5" is decimal.
        cleaned = whole + fraction if len(fraction) == 3 and whole.lstrip("-").isdigit() else whole + "." + fraction
    elif cleaned.count(".") == 1:
        whole, fraction = cleaned.split(".")
        # "48.500" is 48500 in European notation; "48.5" stays decimal.
        if len(fraction) == 3 and whole.lstrip("-").isdigit():
            cleaned = whole + fraction
    elif cleaned.count(".") > 1:
        # "1.234.567" — thousands separators only.
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_int(value: Any) -> int | None:
    decimal = to_decimal(value)
    if decimal is None:
        return None
    try:
        return int(decimal)
    except (ValueError, OverflowError):
        return None


def parse_float(value: Any) -> float | None:
    decimal = to_decimal(value)
    return float(decimal) if decimal is not None else None


def parse_date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            # Accept unix seconds and milliseconds.
            seconds = float(value)
            if seconds > 1e11:
                seconds /= 1000.0
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[: len(fmt) + 6], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def normalise_manufacturer(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    key = text.lower()
    if key in MANUFACTURER_ALIASES:
        return MANUFACTURER_ALIASES[key]
    return " ".join(part.capitalize() for part in text.split())


def normalise_currency(value: Any, default: str = "EUR") -> str:
    if not value:
        return default
    key = str(value).strip().lower()
    code = CURRENCY_ALIASES.get(key, key.upper())
    return code[:3] if len(code) >= 3 else default


def currency_rate(currency: str, rates: dict[str, float] | None = None) -> float:
    rates = rates or {"EUR": 1.0}
    return float(rates.get((currency or "EUR").upper(), 1.0))


def price_to_eur(price: float | Decimal | None, currency: str, rates: dict[str, float] | None = None) -> float | None:
    if price is None:
        return None
    return round(float(price) * currency_rate(currency, rates), 2)


def normalise_axle_config(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).lower().replace(" ", "")
    match = re.search(r"(\d)\s*[xX×]\s*(\d)", text)
    if match:
        return f"{match.group(1)}x{match.group(2)}"
    return str(value).strip()[:20]


def completeness(values: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    missing: list[str] = []
    for field, weight in COMPLETENESS_WEIGHTS.items():
        value = values.get(field)
        if value not in (None, "", [], {}):
            score += weight
        else:
            missing.append(field)
    return min(score, 100), missing


def validate_listing(values: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    year = values.get("year")
    current_year = datetime.now(timezone.utc).year
    if year is not None:
        if year > current_year + 1:
            warnings.append(f"Production year {year} is in the future")
        elif year < 1950:
            warnings.append(f"Production year {year} is implausible")
    price = values.get("price")
    if price is not None and float(price) <= 0:
        warnings.append("Price is zero or negative")
    mileage = values.get("mileage_km")
    if mileage is not None:
        if mileage < 0:
            warnings.append("Mileage is negative")
        elif mileage > 3_000_000:
            warnings.append("Mileage exceeds 3,000,000 km")
    url = values.get("original_url") or ""
    if url and not url.lower().startswith(("http://", "https://")):
        warnings.append("Original listing URL is not absolute")
    for field in CRITICAL_FIELDS:
        if values.get(field) in (None, ""):
            warnings.append(f"Missing {field.replace('_', ' ')}")
    return warnings


def fingerprint(values: dict[str, Any]) -> str:
    parts = [
        str(values.get("manufacturer") or "").lower(),
        str(values.get("model") or "").lower(),
        str(values.get("year") or ""),
        str(values.get("mileage_km") or ""),
        str(int(float(values.get("price"))) if values.get("price") else ""),
        str(values.get("country") or "").upper(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
