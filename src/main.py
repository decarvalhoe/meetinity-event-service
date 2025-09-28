"""Meetinity Event Service using SQLAlchemy for persistence."""

from flask import Flask, jsonify, request, g

from src.database import get_session, init_engine
from src.services.events import EventNotFoundError, EventService, ValidationError

app = Flask(__name__)


# Initialise the database engine using environment configuration.
init_engine()


def get_event_service() -> EventService:
    """Return a lazily initialised :class:`EventService` for the request."""

    if "db_session" not in g:
        g.db_session = get_session()
    if "event_service" not in g:
        g.event_service = EventService(g.db_session)
    return g.event_service


@app.teardown_appcontext
def shutdown_session(exception):
    """Ensure the SQLAlchemy session is properly closed after each request."""

    session = g.pop("db_session", None)
    g.pop("event_service", None)
    if session is not None:
        try:
            if exception is not None:
                session.rollback()
        finally:
            session.close()


def error_response(status: int, message: str, details=None):
    """Create a standardized error response.

    Args:
        status (int): HTTP status code.
        message (str): Error message.
        details (dict, optional): Additional error details.

    Returns:
        tuple: JSON response and status code.
    """
    payload = {"error": {"code": status, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


@app.route("/health")
def health():
    """Health check endpoint.

    Returns:
        Response: JSON response with service status.
    """
    return jsonify({"status": "ok", "service": "event-service"})


@app.route("/events")
def get_events():
    """Retrieve list of available events with optional filters."""

    service = get_event_service()

    try:
        events = service.list_events(
            event_type=request.args.get("type"),
            location=request.args.get("location"),
            before=request.args.get("before"),
            after=request.args.get("after"),
        )
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)

    return jsonify({"events": events})


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


@app.errorhandler(404)
def handle_404(e):
    """Handle 404 Not Found errors.

    Args:
        e: The error object.

    Returns:
        Response: Standardized 404 error response.
    """
    return error_response(404, "Ressource introuvable.")


@app.errorhandler(405)
def handle_405(e):
    """Handle 405 Method Not Allowed errors.

    Args:
        e: The error object.

    Returns:
        Response: Standardized 405 error response.
    """
    return error_response(405, "Méthode non autorisée pour cette ressource.")


@app.errorhandler(500)
def handle_500(e):
    """Handle 500 Internal Server Error.

    Args:
        e: The error object.

    Returns:
        Response: Standardized 500 error response.
    """
    return error_response(500, "Erreur interne. On respire, on relance.")


if __name__ == "__main__":
    app.run(debug=True, port=5003)
