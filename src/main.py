"""Meetinity Event Service.

This service handles event management, creation, and discovery
for professional networking events on the Meetinity platform.
"""

from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)


# In-memory storage for events. This mimics a lightweight persistence layer
# for the purposes of the current application scope.
_INITIAL_EVENTS = [
    {
        "id": 1,
        "title": "Networking Night Paris",
        "date": "2025-08-15",
        "location": "Paris",
        "type": "networking",
        "attendees": 45,
    },
    {
        "id": 2,
        "title": "Tech Meetup Lyon",
        "date": "2025-08-20",
        "location": "Lyon",
        "type": "tech",
        "attendees": 32,
    },
]


def _reset_events_storage():
    """Reset the in-memory storage to its initial state."""
    global _events_storage, _next_event_id
    _events_storage = [event.copy() for event in _INITIAL_EVENTS]
    _next_event_id = (
        max(event["id"] for event in _events_storage) + 1
        if _events_storage
        else 1
    )


_events_storage = []
_next_event_id = 1
_reset_events_storage()


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


def validate_event(data: dict):
    """Validate event data for creation/update operations.
    
    Args:
        data (dict): Event data to validate.
        
    Returns:
        tuple: (is_valid: bool, errors: dict)
    """
    errors = {}

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.setdefault("title", []).append("Champ requis (string non vide).")

    if "attendees" in data:
        att = data["attendees"]
        if (
            not isinstance(att, int)
            or isinstance(att, bool)
            or att < 0
        ):
            errors.setdefault("attendees", []).append(
                "Doit être un entier non booléen >= 0."
            )

    return len(errors) == 0, errors


@app.route("/health")
def health():
    """Health check endpoint.
    
    Returns:
        Response: JSON response with service status.
    """
    return jsonify({"status": "ok", "service": "event-service"})


@app.route("/events")
def get_events():
    """Retrieve list of available events.
    
    Returns:
        Response: JSON response with events list.
    """
    return jsonify({"events": [event.copy() for event in _events_storage]})


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

    is_valid, errors = validate_event(data)
    if not is_valid:
        return error_response(422, "Validation échouée.", errors)

    global _next_event_id

    new_event = {
        "id": _next_event_id,
        "title": data["title"].strip(),
        "date": data.get("date")
        or datetime.today().strftime("%Y-%m-%d"),
        "location": data.get("location") or "TBD",
        "type": data.get("type") or "general",
        "attendees": data.get("attendees", 0),
    }

    _events_storage.append(new_event)
    _next_event_id += 1

    return (
        jsonify(
            {
                "message": "Event created",
                "event_id": new_event["id"],
                "event": new_event,
            }
        ),
        201,
    )


@app.route("/events/<int:event_id>")
def get_event(event_id):
    """Retrieve details for a specific event.
    
    Args:
        event_id (int): The ID of the event to retrieve.
        
    Returns:
        Response: JSON response with event details.
    """
    event = next(
        (stored_event for stored_event in _events_storage if stored_event["id"] == event_id),
        None,
    )

    if event is None:
        return error_response(404, "Événement introuvable.")

    return jsonify({"event": event.copy()})


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
