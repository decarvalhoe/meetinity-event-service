"""Routes for managing event tags."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_tag_service
from src.routes.utils import error_response
from src.services.events import ValidationError

tags_bp = Blueprint("event_tags", __name__)


@tags_bp.get("/event-tags")
def list_tags():
    service = get_tag_service()
    tags = service.list_tags()
    return jsonify({"tags": tags})


@tags_bp.post("/event-tags")
def create_tag():
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
    service = get_tag_service()
    try:
        tag = service.create_tag(data)
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"tag": tag}), 201


@tags_bp.get("/event-tags/<int:tag_id>")
def get_tag(tag_id: int):
    service = get_tag_service()
    try:
        tag = service.get_tag(tag_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return jsonify({"tag": tag})


@tags_bp.route("/event-tags/<int:tag_id>", methods=["PUT", "PATCH"])
def update_tag(tag_id: int):
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
    service = get_tag_service()
    try:
        tag = service.update_tag(tag_id, data)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return jsonify({"tag": tag})


@tags_bp.delete("/event-tags/<int:tag_id>")
def delete_tag(tag_id: int):
    service = get_tag_service()
    try:
        service.delete_tag(tag_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return ("", 204)
