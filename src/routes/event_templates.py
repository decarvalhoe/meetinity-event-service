"""Routes for managing event templates."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_template_service
from src.routes.utils import error_response
from src.services.events import ValidationError

templates_bp = Blueprint("event_templates", __name__)


@templates_bp.get("/event-templates")
def list_templates():
    service = get_template_service()
    templates = service.list_templates()
    return jsonify({"templates": templates})


@templates_bp.post("/event-templates")
def create_template():
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
    service = get_template_service()
    try:
        template = service.create_template(data)
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"template": template}), 201


@templates_bp.get("/event-templates/<int:template_id>")
def get_template(template_id: int):
    service = get_template_service()
    try:
        template = service.get_template(template_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return jsonify({"template": template})


@templates_bp.route("/event-templates/<int:template_id>", methods=["PUT", "PATCH"])
def update_template(template_id: int):
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
    service = get_template_service()
    try:
        template = service.update_template(template_id, data)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return jsonify({"template": template})


@templates_bp.delete("/event-templates/<int:template_id>")
def delete_template(template_id: int):
    service = get_template_service()
    try:
        service.delete_template(template_id)
    except ValidationError as exc:
        return error_response(404, exc.message, exc.errors)
    return ("", 204)


@templates_bp.post("/event-templates/<int:template_id>/translations")
def add_template_translation(template_id: int):
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
    service = get_template_service()
    try:
        translation = service.upsert_translation(template_id, data)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return jsonify({"translation": translation}), 201


@templates_bp.put("/event-templates/<int:template_id>/translations/<locale>")
def update_template_translation(template_id: int, locale: str):
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
    data.setdefault("locale", locale)
    service = get_template_service()
    try:
        translation = service.upsert_translation(template_id, data)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return jsonify({"translation": translation})


@templates_bp.delete("/event-templates/<int:template_id>/translations/<locale>")
def delete_template_translation(template_id: int, locale: str):
    service = get_template_service()
    try:
        service.delete_translation(template_id, locale)
    except ValidationError as exc:
        code = 404 if "id" in exc.errors else 422
        return error_response(code, exc.message, exc.errors)
    return ("", 204)
