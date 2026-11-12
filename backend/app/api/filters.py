"""Query-string → search filter parsing for listing endpoints."""

from __future__ import annotations

from fastapi import Request

RESERVED = {
    "page",
    "page_size",
    "sort",
    "mode",
    "source_id",
    "source_ids",
    "manual_url",
    "kind",
    "include_source_status",
}

MULTI_KEYS = (
    "manufacturer",
    "country",
    "euro_class",
    "transmission",
    "fuel_type",
    "axle_config",
    "condition",
    "status",
    "city",
)


def filters_from_query(request: Request) -> dict:
    filters: dict = {}
    for key, value in request.query_params.items():
        if key in RESERVED or value in ("", None):
            continue
        values = [v for v in request.query_params.getlist(key) if v != ""]
        if key in MULTI_KEYS and len(values) > 1:
            filters[key] = values
        else:
            filters[key] = value
    return filters


def source_ids_from_query(request: Request) -> list[str]:
    ids: list[str] = []
    for value in request.query_params.getlist("source_ids"):
        ids.extend([v for v in value.split(",") if v])
    single = request.query_params.get("source_id")
    if single:
        ids.append(single)
    return list(dict.fromkeys(ids))


def bools(filters: dict) -> dict:
    out = dict(filters)
    for key in ("price_changed_only", "with_image", "review_only"):
        if key in out:
            out[key] = str(out[key]).lower() in ("1", "true", "yes", "on")
    return out
