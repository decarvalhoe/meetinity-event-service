"""Meetinity Event Service.

This service handles event management, creation, and discovery
for professional networking events on the Meetinity platform.
"""

from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)


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

    if "date" in data:
        date_value = data.get("date")
        if not isinstance(date_value, str) or not date_value.strip():
            errors.setdefault("date", []).append(
                "Doit être une chaîne au format YYYY-MM-DD."
            )
        else:
            try:
                datetime.strptime(date_value.strip(), "%Y-%m-%d")
            except ValueError:
                errors.setdefault("date", []).append(
                    "Format de date invalide, attendu YYYY-MM-DD."
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
    events = [
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

    is_valid, errors = validate_event(data)
    if not is_valid:
        return error_response(422, "Validation échouée.", errors)

    provided_date = data.get("date")
    if isinstance(provided_date, str):
        provided_date = provided_date.strip()

    new_event = {
        "id": 123,  # TODO: replace with real ID from database
        "title": data["title"].strip(),
        "date": provided_date
        or datetime.today().strftime("%Y-%m-%d"),
        "location": data.get("location") or "TBD",
        "type": data.get("type") or "general",
        "attendees": data.get("attendees", 0),
    }

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
    event = {
        "id": event_id,
        "title": "Sample Event",
        "date": "2025-08-15",
        "location": "Paris",
        "description": (
            "Networking event for professionals"
        ),
    }
    return jsonify({"event": event})


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
