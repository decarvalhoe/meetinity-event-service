"""Client for interacting with the user service REST API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import ServiceConfig, get_service_config

from .base import HttpClient


class UserServiceClient(HttpClient):
    """Expose high level operations for the user service."""

    def __init__(
        self,
        *,
        config: Optional[ServiceConfig] = None,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if config is None:
            config = get_service_config("user_service")
        super().__init__(config, session=session)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        response = self.request("GET", f"users/{user_id}")
        return response.get("data", response)

    def update_preferences(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.request("PUT", f"users/{user_id}/preferences", json_payload=payload)
        return response.get("data", response)

    def search(self, query: str, *, limit: int = 25) -> Dict[str, Any]:
        params = {"q": query, "limit": limit}
        return self.request("GET", "users/search", params=params)

