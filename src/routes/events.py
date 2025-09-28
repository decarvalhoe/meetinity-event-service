"""Routes for managing events and related workflows."""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from src.routes.dependencies import (
    get_event_service,
    get_feedback_service,
    get_networking_service,
    get_speaker_service,
    get_sponsor_service,
)
from src.routes.utils import error_response
from src.services.events import (
    ApprovalWorkflowError,
    EventNotFoundError,
    ValidationError,
)
from src.services.calendar import generate_ics_feed
from src.services.feedback import FeedbackNotFoundError, FeedbackValidationError
from src.services.networking import NetworkingValidationError, ProfileNotFoundError
from src.services.participants import (
    SpeakerNotFoundError,
    SpeakerValidationError,
    SponsorNotFoundError,
    SponsorValidationError,
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


@events_bp.get("/events/calendar")
def events_calendar():
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

    feed = generate_ics_feed(events, calendar_name=request.args.get("name", "Meetinity Events"))
    response = Response(feed, mimetype="text/calendar")
    response.headers["Content-Disposition"] = 'attachment; filename="events.ics"'
    return response


@events_bp.get("/events/map")
def events_map():
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

    features = []
    for event in events:
        coordinates = _extract_geo_coordinates(event)
        if not coordinates:
            continue
        properties = {
            "id": event.get("id"),
            "title": event.get("title"),
            "date": event.get("date"),
            "location": event.get("location"),
            "categories": [category.get("name") for category in event.get("categories", [])],
            "tags": [tag.get("name") for tag in event.get("tags", [])],
            "share_url": (event.get("share") or {}).get("url"),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [coordinates["lon"], coordinates["lat"]]},
                "properties": properties,
            }
        )

    return jsonify({"type": "FeatureCollection", "features": features})


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


@events_bp.post("/events/<int:event_id>/bookmark")
def bookmark_event(event_id: int):
    user_id = _resolve_user_identifier()
    if not user_id:
        return error_response(422, "user_id requis pour enregistrer un favori.")
    service = get_event_service()
    try:
        result = service.bookmark_event(event_id, user_id)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"bookmark": result}), 201


@events_bp.delete("/events/<int:event_id>/bookmark")
def remove_bookmark(event_id: int):
    user_id = _resolve_user_identifier()
    if not user_id:
        return error_response(422, "user_id requis pour retirer un favori.")
    service = get_event_service()
    try:
        result = service.remove_bookmark(event_id, user_id)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    except ValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    return jsonify({"bookmark": result})


@events_bp.get("/events/<int:event_id>/bookmark")
def list_bookmarks(event_id: int):
    service = get_event_service()
    try:
        bookmarks = service.list_bookmarks(event_id)
    except EventNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"bookmarks": bookmarks, "total": len(bookmarks)})


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


def _extract_geo_coordinates(event):
    settings = event.get("settings") if isinstance(event.get("settings"), dict) else None
    candidates = []
    if settings:
        for key in ("coordinates", "geo", "location"):
            value = settings.get(key)
            if isinstance(value, dict):
                candidates.append(value)
    lat = event.get("latitude")
    lon = event.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return {"lat": float(lat), "lon": float(lon)}
    for candidate in candidates:
        c_lat = candidate.get("lat")
        c_lon = candidate.get("lon") or candidate.get("lng")
        if isinstance(c_lat, (int, float)) and isinstance(c_lon, (int, float)):
            return {"lat": float(c_lat), "lon": float(c_lon)}
    return None


def _resolve_user_identifier():
    user_id = None
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            user_id = payload.get("user_id")
    if not user_id:
        user_id = request.args.get("user_id")
    if isinstance(user_id, str):
        return user_id.strip()
    return None


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


@events_bp.post("/events/<int:event_id>/networking/profiles")
def register_networking_profile(event_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_networking_service()
    try:
        profile = service.register_profile(event_id, payload)
    except NetworkingValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except ProfileNotFoundError:
        return error_response(404, "Événement ou profil introuvable.")
    return jsonify({"profile": profile}), 201


@events_bp.get("/events/<int:event_id>/networking/profiles")
def list_networking_profiles(event_id: int):
    service = get_networking_service()
    try:
        profiles = service.list_profiles(event_id)
    except ProfileNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"profiles": profiles, "total": len(profiles)})


@events_bp.post("/events/<int:event_id>/networking/suggestions")
def generate_networking_suggestions(event_id: int):
    payload = {}
    if request.data:
        if not request.is_json:
            return error_response(415, "Content-Type 'application/json' requis.")
        payload = request.get_json(silent=True) or {}

    email = payload.get("email") or payload.get("participant_email")
    limit = payload.get("limit")
    service = get_networking_service()
    try:
        suggestions = service.generate_suggestions(
            event_id,
            participant_email=email,
            limit=limit if isinstance(limit, int) else 3,
        )
    except NetworkingValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except ProfileNotFoundError:
        return error_response(404, "Événement ou profil introuvable.")
    return jsonify({"suggestions": suggestions})


@events_bp.get("/events/<int:event_id>/networking/suggestions")
def list_networking_suggestions(event_id: int):
    email = request.args.get("email")
    service = get_networking_service()
    try:
        suggestions = service.list_suggestions(event_id, participant_email=email)
    except ProfileNotFoundError:
        return error_response(404, "Événement ou profil introuvable.")
    return jsonify({"suggestions": suggestions, "total": len(suggestions)})


@events_bp.post("/events/<int:event_id>/feedback")
def submit_feedback(event_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_feedback_service()
    try:
        feedback = service.submit_feedback(event_id, payload)
    except FeedbackValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except FeedbackNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"feedback": feedback}), 201


@events_bp.get("/events/<int:event_id>/feedback")
def list_feedback(event_id: int):
    service = get_feedback_service()
    try:
        payload = service.list_feedback(event_id)
    except FeedbackNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify(payload)


@events_bp.patch("/events/<int:event_id>/feedback/<int:feedback_id>")
def moderate_feedback(event_id: int, feedback_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_feedback_service()
    try:
        feedback = service.moderate_feedback(event_id, feedback_id, payload)
    except FeedbackValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except FeedbackNotFoundError:
        return error_response(404, "Feedback introuvable.")
    return jsonify({"feedback": feedback})


@events_bp.get("/events/<int:event_id>/speakers")
def list_speakers(event_id: int):
    role = request.args.get("role")
    service = get_speaker_service()
    try:
        speakers = service.list_profiles(event_id, role=role)
    except SpeakerNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"speakers": speakers, "total": len(speakers)})


@events_bp.post("/events/<int:event_id>/speakers")
def add_speaker(event_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_speaker_service()
    try:
        speaker = service.add_profile(event_id, payload)
    except SpeakerValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except SpeakerNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"speaker": speaker}), 201


@events_bp.patch("/events/<int:event_id>/speakers/<int:speaker_id>")
def update_speaker(event_id: int, speaker_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_speaker_service()
    try:
        speaker = service.update_profile(event_id, speaker_id, payload)
    except SpeakerValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except SpeakerNotFoundError:
        return error_response(404, "Intervenant introuvable.")
    return jsonify({"speaker": speaker})


@events_bp.delete("/events/<int:event_id>/speakers/<int:speaker_id>")
def delete_speaker(event_id: int, speaker_id: int):
    service = get_speaker_service()
    try:
        service.remove_profile(event_id, speaker_id)
    except SpeakerNotFoundError:
        return error_response(404, "Intervenant introuvable.")
    return "", 204


@events_bp.get("/events/<int:event_id>/sponsors")
def list_sponsors(event_id: int):
    service = get_sponsor_service()
    try:
        sponsors = service.list_sponsors(event_id)
    except SponsorNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"sponsors": sponsors, "total": len(sponsors)})


@events_bp.post("/events/<int:event_id>/sponsors")
def add_sponsor(event_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_sponsor_service()
    try:
        sponsor = service.add_sponsor(event_id, payload)
    except SponsorValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except SponsorNotFoundError:
        return error_response(404, "Événement introuvable.")
    return jsonify({"sponsor": sponsor}), 201


@events_bp.patch("/events/<int:event_id>/sponsors/<int:sponsor_id>")
def update_sponsor(event_id: int, sponsor_id: int):
    if not request.is_json:
        return error_response(415, "Content-Type 'application/json' requis.")
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response(400, "JSON invalide ou non parsable.")

    service = get_sponsor_service()
    try:
        sponsor = service.update_sponsor(event_id, sponsor_id, payload)
    except SponsorValidationError as exc:
        return error_response(422, exc.message, exc.errors)
    except SponsorNotFoundError:
        return error_response(404, "Sponsor introuvable.")
    return jsonify({"sponsor": sponsor})


@events_bp.delete("/events/<int:event_id>/sponsors/<int:sponsor_id>")
def delete_sponsor(event_id: int, sponsor_id: int):
    service = get_sponsor_service()
    try:
        service.remove_sponsor(event_id, sponsor_id)
    except SponsorNotFoundError:
        return error_response(404, "Sponsor introuvable.")
    return "", 204
