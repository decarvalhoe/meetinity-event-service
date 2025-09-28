"""Client handling publication to social networks."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import ServiceConfig, get_service_config

from .base import HttpClient


class SocialServiceClient(HttpClient):
    """Automate social media publication flows."""

    def __init__(
        self,
        *,
        config: Optional[ServiceConfig] = None,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if config is None:
            config = get_service_config("social_service")
        super().__init__(config, session=session)

    def exchange_token(self, provider: str, code: str, redirect_uri: str) -> Dict[str, Any]:
        payload = {"provider": provider, "code": code, "redirect_uri": redirect_uri}
        return self.request("POST", "oauth/exchange", json_payload=payload)

    def publish_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request("POST", "shares/event", json_payload=payload)

