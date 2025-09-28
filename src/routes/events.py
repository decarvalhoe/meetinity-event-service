"""Routes for managing events and related workflows."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_event_service
from src.routes.utils import error_response
from src.services.events import (
    ApprovalWorkflowError,
    EventNotFoundError,
    ValidationError,
)

events_bp = Blueprint("events", __name__)


@events_bp.get("/events")
def list_events():
    service = get_event_service()
    try:
        events = service.list_events(
            event_type=request.args.get("type"),
            location=request.args.get("location"),
            before=request.args.get("before"),
            after=request.args.get("after"),
            status=request.args.get("status"),
        )
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"events": events})


@events_bp.post("/events")
def create_event():
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

    service = get_event_service()
    try:
        created_event = service.create_event(data)
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)

    payload = {
        "message": "Event created",
        "event_id": created_event["id"],
        "event": created_event,
    }
    return jsonify(payload), 201


@events_bp.get("/events/<int:event_id>")
def get_event(event_id: int):
    service = get_event_service()
    try:
        event = service.get_event(event_id)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"event": event})


@events_bp.patch("/events/<int:event_id>")
def update_event(event_id: int):
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

    service = get_event_service()
    try:
        updated_event = service.update_event(event_id, data)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)

    return jsonify({"message": "Event updated", "event": updated_event})


@events_bp.post("/events/from-template")
def create_event_from_template():
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
    template_id = data.get("template_id")
    overrides = data.get("overrides", {})
    if not isinstance(template_id, int) or template_id <= 0:
        return error_response(422, "template_id doit être un entier positif.")
    if not isinstance(overrides, dict):
        return error_response(422, "overrides doit être un objet JSON.")

    service = get_event_service()
    try:
        created_event = service.create_event_from_template(template_id, overrides)
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)

    payload = {
        "message": "Event created from template",
        "event_id": created_event["id"],
        "event": created_event,
    }
    return jsonify(payload), 201


@events_bp.post("/events/<int:event_id>/translations")
def add_translation(event_id: int):
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
    service = get_event_service()
    try:
        translation = service.upsert_translation(event_id, data)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"translation": translation}), 201


@events_bp.put("/events/<int:event_id>/translations/<locale>")
def update_translation(event_id: int, locale: str):
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
    service = get_event_service()
    try:
        translation = service.upsert_translation(event_id, data)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"translation": translation})


@events_bp.delete("/events/<int:event_id>/translations/<locale>")
def delete_translation(event_id: int, locale: str):
    service = get_event_service()
    try:
        service.delete_translation(event_id, locale)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return ("", 204)


def _handle_workflow(event_id: int, action: str):
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = {}
    if not isinstance(data, dict):
        return error_response(
            400,
            "Payload JSON invalide: un objet JSON (type dict) est requis.",
        )
    actor = data.get("actor")
    notes = data.get("notes")
    service = get_event_service()
    try:
        if action == "submit":
            result = service.submit_for_approval(event_id, actor, notes)
        elif action == "approve":
            result = service.approve_event(event_id, actor, notes)
        elif action == "reject":
            result = service.reject_event(event_id, actor, notes)
        else:
            return error_response(400, "Action de workflow inconnue.")
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ApprovalWorkflowError as exc:
        return error_response(409, str(exc))
    return jsonify(result)


@events_bp.post("/events/<int:event_id>/submit")
def submit_event(event_id: int):
    return _handle_workflow(event_id, "submit")


@events_bp.post("/events/<int:event_id>/approve")
def approve_event(event_id: int):
    return _handle_workflow(event_id, "approve")


@events_bp.post("/events/<int:event_id>/reject")
def reject_event(event_id: int):
    return _handle_workflow(event_id, "reject")
