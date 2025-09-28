"""Client for interacting with the matching service via gRPC."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.config import ServiceConfig, get_service_config

from .base import GrpcClient


class MatchingServiceClient:
    """Expose helper methods for the matching service."""

    def __init__(
        self,
        *,
        config: Optional[ServiceConfig] = None,
        channel: Optional[Any] = None,
    ) -> None:
        if config is None:
            config = get_service_config("matching_service")
        self.client = GrpcClient(config, channel=channel)

    def find_matches_for_event(self, event_id: int, *, limit: int = 10) -> Dict[str, Any]:
        payload = {"event_id": event_id, "limit": limit}
        response = self.client.call_unary_unary(
            "/matching.MatchService/FindMatches",
            payload,
            request_serializer=lambda data: json.dumps(data).encode("utf-8"),
            response_deserializer=lambda data: json.loads(data.decode("utf-8")),
        )
        return response

    def record_feedback(self, event_id: int, attendee_id: str, score: int) -> Dict[str, Any]:
        payload = {"event_id": event_id, "attendee_id": attendee_id, "score": score}
        response = self.client.call_unary_unary(
            "/matching.MatchService/RecordFeedback",
            payload,
            request_serializer=lambda data: json.dumps(data).encode("utf-8"),
            response_deserializer=lambda data: json.loads(data.decode("utf-8")),
        )
        return response

