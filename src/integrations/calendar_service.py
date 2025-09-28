"""Client for synchronising events with external calendars."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import ServiceConfig, get_service_config

from .base import HttpClient


class CalendarServiceClient(HttpClient):
    """Wraps calls to the calendar integration service."""

    def __init__(
        self,
        *,
        config: Optional[ServiceConfig] = None,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if config is None:
            config = get_service_config("calendar_service")
        super().__init__(config, session=session)

    def sync_event(self, event_payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request("POST", "calendars/sync", json_payload=event_payload)

    def remove_event(self, external_id: str) -> Dict[str, Any]:
        return self.request("DELETE", f"calendars/{external_id}")

