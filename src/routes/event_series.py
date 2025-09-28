"""Routes for managing event series."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_series_service
from src.routes.utils import error_response
from src.services.events import ValidationError

series_bp = Blueprint("event_series", __name__)


@series_bp.get("/event-series")
def list_series():
    service = get_series_service()
    series = service.list_series()
    return jsonify({"series": series})


@series_bp.post("/event-series")
def create_series():
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    data = request.get_json(silent=True)
    if data is None:
        return error_response(400, "JSON invalide ou non parsable.")
    if not isinstance(data, dict):
        return error_response(
            400,
            "Payload JSON invalide: un objet JSON (type dict) est requis.",
        )
    service = get_series_service()
    try:
        series = service.create_series(data)
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"series": series}), 201


@series_bp.get("/event-series/<int:series_id>")
def get_series(series_id: int):
    service = get_series_service()
    try:
        series = service.get_series(series_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return jsonify({"series": series})


@series_bp.route("/event-series/<int:series_id>", methods=["PUT", "PATCH"])
def update_series(series_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    data = request.get_json(silent=True)
    if data is None:
        return error_response(400, "JSON invalide ou non parsable.")
    if not isinstance(data, dict):
        return error_response(
            400,
            "Payload JSON invalide: un objet JSON (type dict) est requis.",
        )
    service = get_series_service()
    try:
        series = service.update_series(series_id, data)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return jsonify({"series": series})


@series_bp.delete("/event-series/<int:series_id>")
def delete_series(series_id: int):
    service = get_series_service()
    try:
        service.delete_series(series_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return ("", 204)
