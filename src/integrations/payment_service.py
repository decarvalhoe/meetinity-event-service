"""Client for interacting with the payment service."""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.config import ServiceConfig, get_service_config

from .base import HttpClient


class PaymentServiceClient(HttpClient):
    """Operations supported by the payment service."""

    def __init__(
        self,
        *,
        config: Optional[ServiceConfig] = None,
        session: Optional["requests.Session"] = None,
    ) -> None:
        if config is None:
            config = get_service_config("payment_service")
        super().__init__(config, session=session)

    def capture_payment(
        self,
        *,
        event_id: int,
        attendee_email: str,
        amount: float,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "event_id": event_id,
            "attendee_email": attendee_email,
            "amount": amount,
            "currency": currency,
            "metadata": metadata or {},
        }
        return self.request("POST", "payments/capture", json_payload=payload)

    def refund_payment(self, payment_id: str, *, reason: Optional[str] = None) -> Dict[str, Any]:
        payload = {"reason": reason} if reason else None
        return self.request(
            "POST",
            f"payments/{payment_id}/refund",
            json_payload=payload,
        )

    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        return self.request("GET", f"payments/{payment_id}")

