"""SSRF-guarded outbound HTTP.

Every outbound request made by the discovery engine, the inspector and the
website connectors goes through :func:`safe_request`, which:

* accepts only http/https,
* rejects embedded credentials and internal host names,
* resolves the host and refuses loopback / private / link-local addresses,
* re-validates each redirect hop,
* caps the response body size and the total redirect count.

Tests inject an ``httpx.Client`` (with a mock transport) so no real network call
is made; the validation logic still runs.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "kubernetes.default",
}

ALLOWED_SCHEMES = {"http", "https"}


class OutboundError(Exception):
    """Outbound request refused or failed."""


def _resolved_addresses(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []
    return sorted({info[4][0] for info in infos})


def validate_outbound_url(url: str, *, allow_private: bool | None = None) -> str:
    allow_private = settings.allow_private_outbound if allow_private is None else allow_private
    parsed = urlparse((url or "").strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise OutboundError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise OutboundError("URL has no host")
    if parsed.username or parsed.password:
        raise OutboundError("Credentials in URLs are not allowed")
    if parsed.port and parsed.port not in (80, 443, 8000, 8080, 8443):
        raise OutboundError(f"Port {parsed.port} is not allowed for outbound requests")

    host = parsed.hostname.strip().lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise OutboundError(f"Host {host!r} is not allowed")
    if allow_private:
        return url

    try:
        literal = ipaddress.ip_address(host)
        candidates = [str(literal)]
    except ValueError:
        candidates = _resolved_addresses(host)

    for raw in candidates:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise OutboundError(f"Host resolves to a non-public address ({ip})")
    return url


def default_client() -> httpx.Client:
    return httpx.Client(
        timeout=settings.outbound_timeout_seconds,
        follow_redirects=False,
        headers={"User-Agent": settings.outbound_user_agent},
    )


def safe_request(
    method: str,
    url: str,
    *,
    client: httpx.Client | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json_body: dict | None = None,
    timeout: float | None = None,
    allow_private: bool | None = None,
    max_redirects: int | None = None,
) -> httpx.Response:
    method = (method or "GET").upper()
    if method not in {"GET", "HEAD", "POST", "PUT", "PATCH"}:
        raise OutboundError(f"HTTP method {method} is not allowed")

    max_redirects = settings.outbound_max_redirects if max_redirects is None else max_redirects
    owns_client = client is None
    http = client or default_client()
    current_url = url
    current_method = method
    payload = json_body
    try:
        for hop in range(max_redirects + 1):
            validate_outbound_url(current_url, allow_private=allow_private)
            response = http.request(
                current_method,
                current_url,
                headers=headers,
                params=params,
                json=payload,
                timeout=timeout or settings.outbound_timeout_seconds,
            )
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location or hop >= max_redirects:
                    raise OutboundError("Too many or invalid redirects")
                current_url = urljoin(current_url, location)
                if response.status_code == 303:
                    current_method, payload = "GET", None
                    params = None
                continue
            if len(response.content) > settings.outbound_max_bytes:
                raise OutboundError("Response exceeds the configured size limit")
            return response
        raise OutboundError("Too many redirects")
    except httpx.HTTPError as exc:
        raise OutboundError(f"Request failed: {exc.__class__.__name__}: {exc}") from exc
    finally:
        if owns_client:
            http.close()
