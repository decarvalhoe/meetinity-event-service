"""Meetinity Event Service application entrypoint."""
from __future__ import annotations

from flask import Flask, g, jsonify, request

from src.database import get_session, init_engine
from src.routes import register_blueprints
from src.routes.dependencies import cleanup_services
from src.routes.utils import error_response
from src.services.events import EventNotFoundError, EventService, ValidationError
from src.services.registrations import (
    CheckInError,
    DuplicateRegistrationError,
    PenaltyActiveError,
    RegistrationClosedError,
    RegistrationService,
)

app = Flask(__name__)


def create_app() -> Flask:
    init_engine()
    register_blueprints(app)
    app.teardown_appcontext(cleanup_services)
    register_error_handlers(app)
    return app


def get_event_service() -> EventService:
    """Return a lazily initialised :class:`EventService` for the request."""

    if "db_session" not in g:
        g.db_session = get_session()
    if "event_service" not in g:
        g.event_service = EventService(g.db_session)
    return g.event_service


def get_registration_service() -> RegistrationService:
    """Return a lazily initialised :class:`RegistrationService`."""

    if "db_session" not in g:
        g.db_session = get_session()
    if "registration_service" not in g:
        g.registration_service = RegistrationService(g.db_session)
    return g.registration_service


@app.teardown_appcontext
def shutdown_session(exception):
    """Ensure the SQLAlchemy session is properly closed after each request."""

    session = g.pop("db_session", None)
    g.pop("event_service", None)
    g.pop("registration_service", None)
    if session is not None:
        try:
            if exception is not None:
                session.rollback()
        finally:
            session.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "event-service"}


def register_error_handlers(flask_app: Flask) -> None:
    @flask_app.errorhandler(404)
    def handle_404(e):
        return error_response(404, "Ressource introuvable.")

    @flask_app.errorhandler(405)
    def handle_405(e):
        return error_response(405, "Méthode non autorisée pour cette ressource.")

    @flask_app.errorhandler(500)
    def handle_500(e):
        return error_response(500, "Erreur interne. On respire, on relance.")


@app.route("/events", methods=["POST"])
def create_event():
    """Create a new professional event.

    Expected JSON payload:
        {
            "title": str (required),
            "date": str (optional),
            "location": str (optional),
            "type": str (optional),
            "attendees": int (optional)
        }

    Returns:
        Response: JSON response with created event details.
    """
    if not request.is_json:
        return error_response(
            415, "Content-Type 'application/json' requis."
        )

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


@app.route("/events/<int:event_id>")
def get_event(event_id):
    """Retrieve details for a specific event.

    Args:
        event_id (int): The ID of the event to retrieve.

    Returns:
        Response: JSON response with event details.
    """
    service = get_event_service()

    try:
        event = service.get_event(event_id)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")

    return jsonify({"event": event})


@app.route("/events/<int:event_id>", methods=["PATCH"])
def update_event(event_id):
    """Partially update an existing event."""

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


@app.route("/events/<int:event_id>/registrations", methods=["GET", "POST"])
def manage_registrations(event_id: int):
    service = get_registration_service()

    if request.method == "GET":
        try:
            registrations = service.list_registrations(event_id)
        except LookupError:
            return error_response(404, "Événement introuvable.")
        return jsonify({"registrations": registrations})

    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")

    data = request.get_json(silent=True) or {}
    email = data.get("email")
    name = data.get("name")
    metadata = data.get("metadata") if isinstance(data, dict) else None

    if not isinstance(email, str) or not email.strip():
        return error_response(422, "Validation échouée.", {"email": ["Adresse requise."]})

    try:
        result = service.register_attendee(
            event_id,
            email=email,
            full_name=name if isinstance(name, str) else None,
            metadata=metadata if isinstance(metadata, dict) else None,
        )
    except LookupError:
        return error_response(404, "Événement introuvable.")
    except RegistrationClosedError as exc:
        return error_response(409, str(exc))
    except DuplicateRegistrationError as exc:
        return error_response(409, str(exc))
    except PenaltyActiveError as exc:
        return error_response(403, str(exc))
    except ValueError as exc:
        return error_response(422, "Validation échouée.", {"email": [str(exc)]})

    status_code = 201 if result["status"] == "confirmed" else 202
    return jsonify(result), status_code


@app.route("/events/<int:event_id>/registrations/<int:registration_id>", methods=["DELETE"])
def cancel_registration(event_id: int, registration_id: int):
    service = get_registration_service()
    try:
        result = service.cancel_registration(event_id, registration_id)
    except LookupError:
        return error_response(404, "Inscription introuvable.")
    return jsonify({"message": "Registration cancelled", **result})


@app.route("/events/<int:event_id>/waitlist", methods=["GET", "POST"])
def manage_waitlist(event_id: int):
    service = get_registration_service()
    if request.method == "GET":
        try:
            waitlist = service.list_waitlist(event_id)
        except LookupError:
            return error_response(404, "Événement introuvable.")
        return jsonify({"waitlist": waitlist})

    try:
        promoted = service.trigger_waitlist_promotion(event_id)
    except LookupError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"promoted": promoted})


@app.route("/events/<int:event_id>/attendance", methods=["GET", "POST"])
def manage_attendance(event_id: int):
    service = get_registration_service()
    if request.method == "GET":
        try:
            attendance = service.list_attendance(event_id)
        except LookupError:
            return error_response(404, "Événement introuvable.")
        return jsonify({"attendance": attendance})

    try:
        result = service.detect_no_shows(event_id)
    except LookupError:
        return error_response(404, "Événement introuvable.")
    return jsonify(result)


@app.route("/check-in/<token>", methods=["POST"])
def check_in(token: str):
    service = get_registration_service()
    metadata = None
    method = "qr"
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
            method_value = payload.get("method")
            if isinstance(method_value, str) and method_value.strip():
                method = method_value.strip()
    try:
        result = service.check_in_attendee(token, method=method, metadata=metadata)
    except CheckInError as exc:
        return error_response(400, str(exc))
    except LookupError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"message": "Check-in enregistré", "attendance": result})


create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5003)
