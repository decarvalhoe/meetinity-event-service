"""Client responsible for dispatching transactional emails."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import ServiceConfig, get_service_config

from .base import HttpClient


class EmailServiceClient(HttpClient):
    """Send notifications via the email microservice."""

    def __init__(
        self,
        *,
        config: Optional[ServiceConfig] = None,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if config is None:
            config = get_service_config("email_service")
        super().__init__(config, session=session)

    def send_notification(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request("POST", "notifications/send", json_payload=payload)

