from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)


# ---------- Utils ----------
def error_response(status: int, message: str, details=None):
    payload = {"error": {"code": status, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


def validate_event(data: dict):
    """Retourne (is_valid, errors_dict). Seul 'title' est requis."""
    errors = {}

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.setdefault("title", []).append("Champ requis (string non vide).")

    if "attendees" in data:
        att = data["attendees"]
        if not isinstance(att, int) or att < 0:
            errors.setdefault("attendees", []).append(
                "Doit être un entier >= 0."
            )

    return len(errors) == 0, errors


# ---------- Routes ----------
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "event-service"})


@app.route("/events")
def get_events():
    """Récupérer la liste des événements"""
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
    """Créer un nouvel événement"""
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

    new_event = {
        "id": 123,  # TODO: remplacer par un ID réel (DB/sequence)
        "title": data["title"].strip(),
        "date": data.get("date")
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
    """Récupérer un événement spécifique (mock)"""
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


# ---------- Error handlers ----------
@app.errorhandler(404)
def handle_404(e):
    return error_response(404, "Ressource introuvable.")


@app.errorhandler(405)
def handle_405(e):
    return error_response(405, "Méthode non autorisée pour cette ressource.")


@app.errorhandler(500)
def handle_500(e):
    return error_response(500, "Erreur interne. On respire, on relance.")


if __name__ == "__main__":
    app.run(debug=True, port=5003)
