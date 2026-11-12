"""Curated catalogue of publicly known European truck marketplaces.

These entries are *real websites* used to seed the discovery engine so that a
fresh installation has a starting point. They are deliberately recorded as
``needs_review`` — a catalogue entry is not an access grant. Each site must pass
the robots.txt / compatibility inspection and be approved by an administrator
before KUHHAN will collect from it.
"""

from __future__ import annotations

from typing import TypedDict


class CatalogueEntry(TypedDict):
    domain: str
    name: str
    country: str
    language: str
    category: str


CURATED_SOURCES: list[CatalogueEntry] = [
    {"domain": "autoline.eu", "name": "Autoline", "country": "LT", "language": "en", "category": "marketplace"},
    {"domain": "truckscout24.com", "name": "TruckScout24", "country": "DE", "language": "de", "category": "marketplace"},
    {"domain": "mobile.de", "name": "mobile.de", "country": "DE", "language": "de", "category": "marketplace"},
    {"domain": "truck1.eu", "name": "Truck1", "country": "DE", "language": "en", "category": "marketplace"},
    {"domain": "mascus.com", "name": "Mascus", "country": "NL", "language": "en", "category": "marketplace"},
    {"domain": "allegro.pl", "name": "Allegro", "country": "PL", "language": "pl", "category": "marketplace"},
    {"domain": "olx.pl", "name": "OLX Poland", "country": "PL", "language": "pl", "category": "marketplace"},
    {"domain": "otomoto.pl", "name": "Otomoto", "country": "PL", "language": "pl", "category": "marketplace"},
    {"domain": "autoplius.lt", "name": "Autoplius", "country": "LT", "language": "lt", "category": "marketplace"},
    {"domain": "autogidas.lt", "name": "Autogidas", "country": "LT", "language": "lt", "category": "marketplace"},
    {"domain": "ss.lv", "name": "SS.lv", "country": "LV", "language": "lv", "category": "marketplace"},
    {"domain": "auto24.ee", "name": "Auto24", "country": "EE", "language": "et", "category": "marketplace"},
    {"domain": "marktplaats.nl", "name": "Marktplaats", "country": "NL", "language": "nl", "category": "marketplace"},
    {"domain": "autoscout24.com", "name": "AutoScout24", "country": "DE", "language": "de", "category": "marketplace"},
    {"domain": "bilbasen.dk", "name": "Bilbasen", "country": "DK", "language": "da", "category": "marketplace"},
    {"domain": "blocket.se", "name": "Blocket", "country": "SE", "language": "sv", "category": "marketplace"},
    {"domain": "nettiauto.com", "name": "Nettiauto", "country": "FI", "language": "fi", "category": "marketplace"},
    {"domain": "leboncoin.fr", "name": "Leboncoin", "country": "FR", "language": "fr", "category": "marketplace"},
    {"domain": "2ememain.be", "name": "2ememain", "country": "BE", "language": "nl", "category": "marketplace"},
    {"domain": "trucksnl.com", "name": "Trucks.nl", "country": "NL", "language": "en", "category": "marketplace"},
    {"domain": "camionsupermarket.nl", "name": "Camion Supermarket", "country": "NL", "language": "nl", "category": "dealer_network"},
    {"domain": "kleyn-trucks.eu", "name": "Kleyn Trucks", "country": "NL", "language": "en", "category": "dealer"},
    {"domain": "truckland.eu", "name": "Truckland", "country": "LT", "language": "en", "category": "dealer"},
    {"domain": "agriaffaires.co.uk", "name": "Agriaffaires", "country": "GB", "language": "en", "category": "marketplace"},
    {"domain": "euroauctions.com", "name": "Euro Auctions", "country": "GB", "language": "en", "category": "auction"},
    {"domain": "ritchiebros.eu", "name": "Ritchie Bros.", "country": "NL", "language": "en", "category": "auction"},
    {"domain": "troostwijkauctions.com", "name": "Troostwijk Auctions", "country": "NL", "language": "en", "category": "auction"},
    {"domain": "autoline24.lt", "name": "Autoline Lietuva", "country": "LT", "language": "lt", "category": "marketplace"},
]


def search_catalogue(query: str, limit: int = 25) -> list[CatalogueEntry]:
    """Case-insensitive keyword filter over the curated catalogue."""
    terms = [t for t in query.lower().split() if t]
    if not terms:
        return CURATED_SOURCES[:limit]
    scored: list[tuple[int, CatalogueEntry]] = []
    for entry in CURATED_SOURCES:
        haystack = f"{entry['name']} {entry['domain']} {entry['country']} {entry['category']}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1]["domain"]))
    return [entry for _, entry in scored[:limit]]
