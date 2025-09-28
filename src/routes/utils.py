"""Shared route utilities."""
from __future__ import annotations

from typing import Any, Optional

from flask import jsonify


def error_response(status: int, message: str, details: Optional[Any] = None):
    payload = {"error": {"code": status, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status
