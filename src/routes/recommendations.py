"""Routes exposing personalised recommendations."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.routes.dependencies import get_recommendation_service
from src.routes.utils import error_response

recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.get("/users/<user_id>/recommendations")
def get_recommendations(user_id: str):
    service = get_recommendation_service()
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return error_response(422, "Paramètre limit invalide.")

    recommendations = service.get_recommendations(user_id, limit=max(1, min(limit, 50)))
    return jsonify({"user_id": user_id, "recommendations": recommendations})
