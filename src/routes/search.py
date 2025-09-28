"""Routes exposing the event search API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_search_service
from src.routes.utils import error_response
from src.services.search import SearchError

search_bp = Blueprint("search", __name__)


@search_bp.get("/search/events")
def search_events():
    service = get_search_service()

    try:
        page = int(request.args.get("page", 1))
        size = int(request.args.get("size", 20))
    except ValueError:
        return error_response(422, "Paramètres de pagination invalides.")

    lat, lon, radius = _parse_geo_params()
    include_suggestions = request.args.get("suggest", "true").lower() != "false"

    categories = _parse_list_param("category", "categories")
    tags = _parse_list_param("tag", "tags")
    languages = _parse_list_param("language", "languages")

    try:
        results = service.search_events(
            text=request.args.get("q"),
            categories=categories,
            tags=tags,
            languages=languages,
            start_date=request.args.get("start"),
            end_date=request.args.get("end"),
            lat=lat,
            lon=lon,
            radius_km=radius,
            page=page,
            size=size,
            sort=request.args.get("sort"),
            include_suggestions=include_suggestions,
        )
    except SearchError as exc:
        return error_response(503, str(exc))

    return jsonify(results)


def _parse_list_param(*keys):
    values = []
    for key in keys:
        raw_values = request.args.getlist(key)
        for value in raw_values:
            if value:
                values.extend(part.strip() for part in value.split(",") if part.strip())
    return values


def _parse_geo_params():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    radius = request.args.get("radius") or request.args.get("radius_km")
    try:
        lat_value = float(lat) if lat is not None else None
        lon_value = float(lon) if lon is not None else None
        radius_value = float(radius) if radius is not None else None
    except ValueError:
        return None, None, None
    return lat_value, lon_value, radius_value
