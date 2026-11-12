"""Website inspector.

Given a URL, KUHHAN fetches the public page, robots.txt and on-page metadata and
produces an evidence-based analysis report. Nothing is assumed: every field is
either observed, absent, or explicitly marked as unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.http import OutboundError, safe_request

TRUCK_KEYWORDS = (
    "truck",
    "trucks",
    "lkw",
    "lastwagen",
    "camion",
    "camions",
    "vrachtwagen",
    "ciężarow",
    "ciezarow",
    "kamyon",
    "kuorma-auto",
    "lastbil",
    "veoauto",
    "sunkvežim",
    "sunkvezim",
    "man tgx",
    "actros",
    "volvo fh",
    "scania r",
    "daf xf",
    "iveco stralis",
    "renault t",
    "tractor unit",
    "semi truck",
    "trailer",
    "heavy duty",
    "commercial vehicle",
)

LISTING_PATH_HINTS = (
    "listing",
    "listings",
    "offer",
    "offers",
    "shop",
    "catalog",
    "catalogue",
    "fahrzeug",
    "fahrzeuge",
    "skelbim",
    "sludinajum",
    "kuulutus",
    "ocasion",
    "occasions",
    "anuncios",
    "voertuig",
    "voertuigen",
    "trucks",
    "lkw",
    "camions",
    "sortiment",
    "inventory",
    "stock",
)

API_DOC_HINTS = ("/api", "/swagger", "/openapi.json", "/api-docs", "/docs", "/developer", "/developers")
TERMS_HINTS = ("/terms", "/tos", "/terms-of-use", "/conditions", "/legal", "/privacy")

TLD_COUNTRY = {
    "lt": "LT",
    "lv": "LV",
    "ee": "EE",
    "pl": "PL",
    "de": "DE",
    "nl": "NL",
    "be": "BE",
    "fr": "FR",
    "dk": "DK",
    "se": "SE",
    "fi": "FI",
    "gb": "GB",
    "uk": "GB",
    "ie": "IE",
    "es": "ES",
    "it": "IT",
    "at": "AT",
    "ch": "CH",
    "cz": "CZ",
    "sk": "SK",
    "hu": "HU",
    "ro": "RO",
    "bg": "BG",
    "si": "SI",
    "hr": "HR",
    "no": "NO",
    "eu": None,
    "com": None,
}

KNOWN_MULTI_PART_SUFFIXES = ("co.uk", "com.pl", "co.za", "org.uk", "com.au")


@dataclass
class InspectionReport:
    url: str
    domain: str
    title: str = ""
    description: str = ""
    http_status: int | None = None
    language: str | None = None
    country: str | None = None
    truck_keyword_hits: list[str] = field(default_factory=list)
    listing_candidates: list[str] = field(default_factory=list)
    api_doc_candidates: list[str] = field(default_factory=list)
    terms_url: str | None = None
    robots_url: str | None = None
    robots_allows_root: bool | None = None
    robots_blocks_all: bool | None = None
    robots_notes: str = ""
    sitemap_url: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "description": self.description,
            "http_status": self.http_status,
            "language": self.language,
            "country": self.country,
            "truck_keyword_hits": self.truck_keyword_hits,
            "listing_candidates": self.listing_candidates,
            "api_doc_candidates": self.api_doc_candidates,
            "terms_url": self.terms_url,
            "robots_url": self.robots_url,
            "robots_allows_root": self.robots_allows_root,
            "robots_blocks_all": self.robots_blocks_all,
            "robots_notes": self.robots_notes,
            "sitemap_url": self.sitemap_url,
            "error": self.error,
        }


def extract_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip(".")
    if not host:
        raise ValueError("URL has no host")
    if host.startswith("www."):
        host = host[4:]
    return host


def country_from_domain(domain: str) -> str | None:
    for suffix in KNOWN_MULTI_PART_SUFFIXES:
        if domain.endswith("." + suffix):
            return TLD_COUNTRY.get(suffix.split(".")[-1])
    tld = domain.rsplit(".", 1)[-1]
    return TLD_COUNTRY.get(tld)


def normalise_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ValueError("Website URL is required")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs can be added")
    if not parsed.hostname:
        raise ValueError("The URL does not contain a valid host")
    if "." not in parsed.hostname and parsed.hostname != "localhost":
        raise ValueError("Enter a full website address, e.g. https://example.com")
    if parsed.query or parsed.fragment:
        # A source is a website, not a single search result URL.
        url = parsed._replace(query="", fragment="").geturl()
    return url.rstrip("/")


def _robots(domain: str, client, report: InspectionReport) -> None:
    url = f"https://{domain}/robots.txt"
    report.robots_url = url
    try:
        response = safe_request("GET", url, client=client)
    except OutboundError as exc:
        report.robots_notes = f"robots.txt could not be read: {exc}"
        return
    if response.status_code >= 400:
        report.robots_notes = f"robots.txt returned HTTP {response.status_code} (no rules published)"
        return
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    agent = "*"
    report.robots_allows_root = parser.can_fetch(agent, f"https://{domain}/")
    report.robots_blocks_all = not report.robots_allows_root and not parser.can_fetch(
        agent, f"https://{domain}/listing"
    )
    sitemaps = [line.split(":", 1)[1].strip() for line in response.text.splitlines() if line.lower().startswith("sitemap:")]
    report.sitemap_url = sitemaps[0] if sitemaps else None
    rules = [
        line.strip()
        for line in response.text.splitlines()
        if line.strip().lower().startswith(("disallow:", "allow:", "crawl-delay:"))
    ]
    report.robots_notes = (
        f"robots.txt read ({len(rules)} rules). Root allowed for '*': {report.robots_allows_root}."
    )


def inspect_website(url: str, *, client=None) -> InspectionReport:
    normalised = normalise_url(url)
    domain = extract_domain(normalised)
    report = InspectionReport(url=normalised, domain=domain)
    report.country = country_from_domain(domain)

    _robots(domain, client, report)

    try:
        response = safe_request("GET", normalised, client=client)
    except OutboundError as exc:
        report.error = str(exc)
        return report

    report.http_status = response.status_code
    if response.status_code >= 400:
        report.error = f"Homepage returned HTTP {response.status_code}"
        return report

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and content_type:
        report.error = f"Homepage is not HTML ({content_type})"
        return report

    soup = BeautifulSoup(response.text, "html.parser")
    report.title = (soup.title.string or "").strip()[:300] if soup.title else ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        report.description = meta_desc["content"].strip()[:500]
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        report.language = str(html_tag["lang"]).split("-")[0].lower()[:8]

    text = soup.get_text(" ", strip=True).lower()
    hits = sorted({kw for kw in TRUCK_KEYWORDS if kw in text})
    report.truck_keyword_hits = hits[:20]

    listing_links: dict[str, int] = {}
    api_links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        label = (anchor.get_text(" ", strip=True) or "").lower()
        absolute = urljoin(normalised + "/", href)
        if urlparse(absolute).netloc and domain not in urlparse(absolute).netloc:
            continue
        path = urlparse(absolute).path.lower()
        if any(hint in path for hint in LISTING_PATH_HINTS) or any(hint in label for hint in ("trucks for sale", "used trucks", "lkw kaufen", "camions")):
            listing_links[absolute] = listing_links.get(absolute, 0) + 1
        if any(path.startswith(hint) or hint in path for hint in API_DOC_HINTS) and "api" in path:
            api_links.add(absolute)
        if any(hint in path for hint in TERMS_HINTS) and not report.terms_url:
            report.terms_url = absolute

    report.listing_candidates = [u for u, _ in sorted(listing_links.items(), key=lambda kv: -kv[1])][:10]
    report.api_doc_candidates = sorted(api_links)[:5]
    return report


def build_analysis(report: InspectionReport) -> dict:
    """Turn raw inspection evidence into a compatibility assessment."""
    truck_hits = len(report.truck_keyword_hits)
    has_listings = bool(report.listing_candidates)
    api_docs = report.api_doc_candidates

    if report.error:
        status = "temporarily_unavailable"
        access_method = "manual"
        summary = f"Website could not be inspected: {report.error}"
    elif report.robots_blocks_all:
        status = "manual_access_only"
        access_method = "manual"
        summary = "robots.txt disallows automated crawling of the site; manual research only."
    elif truck_hits >= 2 and has_listings:
        status = "needs_review"
        access_method = "api" if api_docs else "html"
        summary = (
            "Truck listings detected and crawling is permitted by robots.txt. "
            "Administrator approval is required before collection starts."
        )
    elif truck_hits >= 2:
        status = "needs_review"
        access_method = "html"
        summary = "Truck-related content detected but no listing page was identified automatically."
    else:
        status = "under_investigation"
        access_method = "manual"
        summary = "No truck inventory signals were found on the homepage; manual review required."

    compatibility = {
        "truck_signals": truck_hits,
        "listing_pages_found": len(report.listing_candidates),
        "api_documentation_found": bool(api_docs),
        "robots_allows_crawl": report.robots_allows_root,
        "robots_blocks_all": report.robots_blocks_all,
        "terms_url": report.terms_url,
        "html_collection_viable": bool(has_listings and report.robots_allows_root),
        "api_collection_viable": bool(api_docs),
        "outbound_user_agent": settings.outbound_user_agent,
        "recommended_status": status,
        "recommended_access_method": access_method,
        "summary": summary,
        "notes": [
            "robots.txt is advisory for crawlers; the site terms of service remain authoritative.",
            "KUHHAN never bypasses authentication, CAPTCHA, paywalls or anti-bot controls.",
        ],
    }
    return {
        "name": report.title or report.domain,
        "country": report.country,
        "language": report.language,
        "listing_url": report.listing_candidates[0] if report.listing_candidates else None,
        "api_doc_url": api_docs[0] if api_docs else None,
        "terms_url": report.terms_url,
        "has_official_api": bool(api_docs),
        "robots_allowed": report.robots_allows_root,
        "robots_notes": report.robots_notes,
        "status": status,
        "access_method": access_method,
        "compatibility": compatibility,
        "report": report.as_dict(),
    }
