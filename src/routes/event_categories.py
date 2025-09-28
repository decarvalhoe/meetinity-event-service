"""Routes for managing event categories."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_category_service
from src.routes.utils import error_response
from src.services.events import ValidationError

categories_bp = Blueprint("event_categories", __name__)


@categories_bp.get("/event-categories")
def list_categories():
    service = get_category_service()
    categories = service.list_categories()
    return jsonify({"categories": categories})


@categories_bp.post("/event-categories")
def create_category():
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
    service = get_category_service()
    try:
        category = service.create_category(data)
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"category": category}), 201


@categories_bp.get("/event-categories/<int:category_id>")
def get_category(category_id: int):
    service = get_category_service()
    try:
        category = service.get_category(category_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return jsonify({"category": category})


@categories_bp.route("/event-categories/<int:category_id>", methods=["PUT", "PATCH"])
def update_category(category_id: int):
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
    service = get_category_service()
    try:
        category = service.update_category(category_id, data)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return jsonify({"category": category})


@categories_bp.delete("/event-categories/<int:category_id>")
def delete_category(category_id: int):
    service = get_category_service()
    try:
        service.delete_category(category_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return ("", 204)
