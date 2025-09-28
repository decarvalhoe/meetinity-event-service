"""Meetinity Event Service.

This service handles event management, creation, and discovery
for professional networking events on the Meetinity platform.
"""

from flask import Flask, jsonify, request
from datetime import datetime
from itertools import count

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
    global _events_storage, _event_id_counter
    _events_storage = [event.copy() for event in _INITIAL_EVENTS]
    highest_id = max((event["id"] for event in _events_storage), default=0)
    _event_id_counter = count(start=highest_id + 1)


_events_storage = []
_event_id_counter = count(start=1)
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


def validate_event(data: dict, *, require_title: bool = True):
    """Validate event data for creation/update operations.

    Args:
        data (dict): Event data to validate.

    Returns:
        tuple: (is_valid: bool, errors: dict)
    """
    if not isinstance(data, dict):
        return False, {
            "_schema": [
                {
                    "code": 400,
                    "message": "Objet JSON requis pour l'évènement.",
                }
            ]
        }

    errors = {}

    title = data.get("title")
    if "title" in data or require_title:
        if not isinstance(title, str) or not title or not title.strip():
            errors.setdefault("title", []).append(
                "Champ requis (string non vide)."
            )

    if "attendees" in data:
        att = data["attendees"]
        if isinstance(att, bool) or not isinstance(att, int) or att < 0:
            errors.setdefault("attendees", []).append(
                "Doit être un entier >= 0 (valeur booléenne non autorisée)."
            )

    if "date" in data:
        date_value = data.get("date")
        if not isinstance(date_value, str):
            errors.setdefault("date", []).append(
                "Doit être une chaîne au format YYYY-MM-DD."
            )
        else:
            stripped_date = date_value.strip()
            if not stripped_date:
                errors.setdefault("date", []).append(
                    "Doit être une chaîne au format YYYY-MM-DD."
                )
            else:
                try:
                    datetime.strptime(stripped_date, "%Y-%m-%d")
                except ValueError:
                    errors.setdefault("date", []).append(
                        "Format de date invalide, attendu YYYY-MM-DD."
                    )

    return len(errors) == 0, errors


def _parse_filter_date(value: str, field_name: str):
    """Parse a date filter value and return a tuple of (date, error)."""

    if not value:
        return None, None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date(), None
    except ValueError:
        return None, {
            field_name: [
                "Format de date invalide pour le filtre, attendu YYYY-MM-DD."
            ]
        }


@app.route("/health")
def health():
    """Health check endpoint.

    Returns:
        Response: JSON response with service status.
    """
    return jsonify({"status": "ok", "service": "event-service"})


@app.route("/events")
def get_events():
    """Retrieve list of available events with optional filters.

    Returns:
        Response: JSON response with filtered events list.
    """

    event_type = request.args.get("type")
    location = request.args.get("location")
    before = request.args.get("before")
    after = request.args.get("after")

    event_type = (
        event_type.strip() if isinstance(event_type, str) else event_type
    )
    location = (
        location.strip() if isinstance(location, str) else location
    )
    before = before.strip() if isinstance(before, str) else before
    after = after.strip() if isinstance(after, str) else after

    if event_type == "":
        event_type = None

    if location == "":
        location = None

    if before == "":
        before = None

    if after == "":
        after = None

    filter_errors = {}
    before_date = after_date = None

    if before:
        before_date, err = _parse_filter_date(before, "before")
        if err:
            filter_errors.update(err)

    if after:
        after_date, err = _parse_filter_date(after, "after")
        if err:
            filter_errors.update(err)

    if filter_errors:
        return error_response(422, "Validation échouée.", filter_errors)

    def matches_filters(event):
        matches = True

        if event_type:
            matches = matches and (
                str(event.get("type", "")).casefold() == event_type.casefold()
            )

        if matches and location:
            matches = matches and (
                str(event.get("location", "")).casefold()
                == location.casefold()
            )

        if matches and (before_date or after_date):
            try:
                event_date = datetime.strptime(
                    event.get("date"), "%Y-%m-%d"
                ).date()
            except (TypeError, ValueError):
                return False

            if before_date and event_date > before_date:
                return False

            if after_date and event_date < after_date:
                return False

        return matches

    filtered_events = [
        event.copy()
        for event in _events_storage
        if matches_filters(event)
    ]

    return jsonify({"events": filtered_events})


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

    is_valid, errors = validate_event(data, require_title=True)
    if not is_valid:
        return error_response(422, "Validation échouée.", errors)

    provided_date = data.get("date")
    if isinstance(provided_date, str):
        provided_date = provided_date.strip()

    new_event = {
        "id": next(_event_id_counter),
        "title": data["title"].strip(),
        "date": provided_date
        or datetime.today().strftime("%Y-%m-%d"),
        "location": data.get("location") or "TBD",
        "type": data.get("type") or "general",
        "attendees": data.get("attendees", 0),
    }

    _events_storage.append(new_event)

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
        (
            stored_event
            for stored_event in _events_storage
            if stored_event["id"] == event_id
        ),
        None,
    )

    if event is None:
        return error_response(404, "Événement introuvable.")

    return jsonify({"event": event.copy()})


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

    is_valid, errors = validate_event(data, require_title=False)
    if not is_valid:
        return error_response(422, "Validation échouée.", errors)

    event = next(
        (
            stored_event
            for stored_event in _events_storage
            if stored_event["id"] == event_id
        ),
        None,
    )

    if event is None:
        return error_response(404, "Événement introuvable.")

    updates = {}
    if "title" in data:
        updates["title"] = data["title"].strip()

    if "date" in data:
        date_value = data.get("date")
        updates["date"] = (
            date_value.strip() if isinstance(date_value, str) else date_value
        )

    for optional_key in ("location", "type"):
        if optional_key in data:
            value = data.get(optional_key)
            if isinstance(value, str):
                updates[optional_key] = value.strip()
            else:
                updates[optional_key] = value

    if "attendees" in data:
        updates["attendees"] = data["attendees"]

    event.update(updates)

    return jsonify({"message": "Event updated", "event": event.copy()})


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
