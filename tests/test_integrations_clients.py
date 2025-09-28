"""Integration client tests relying on mocked HTTP/gRPC backends."""
from __future__ import annotations

import json
from typing import Any, Dict

import responses

from src.config import ResilienceConfig, ServiceConfig
from src.integrations.calendar_service import CalendarServiceClient
from src.integrations.email_service import EmailServiceClient
from src.integrations.matching_service import MatchingServiceClient
from src.integrations.payment_service import PaymentServiceClient
from src.integrations.social_service import SocialServiceClient
from src.integrations.user_service import UserServiceClient


def _service_config(name: str, base_url: str) -> ServiceConfig:
    return ServiceConfig(
        name=name,
        base_url=base_url,
        protocol="http" if not base_url.startswith("localhost") else "grpc",
        timeout=1.0,
        resilience=ResilienceConfig(
            max_attempts=1,
            backoff_factor=0.01,
            max_backoff=0.01,
            circuit_breaker_failure_threshold=5,
            circuit_breaker_reset_timeout=0.01,
        ),
    )


@responses.activate
def test_user_service_client_fetches_profile() -> None:
    config = _service_config("user_service", "http://users.test")
    responses.add(
        responses.GET,
        "http://users.test/users/42",
        json={"data": {"user_id": "42", "email": "user@example.com"}},
        status=200,
    )
    client = UserServiceClient(config=config)
    profile = client.get_user_profile("42")
    assert profile["user_id"] == "42"
    assert profile["email"] == "user@example.com"


@responses.activate
def test_payment_service_capture_and_refund() -> None:
    config = _service_config("payment_service", "http://payments.test")
    responses.add(
        responses.POST,
        "http://payments.test/payments/capture",
        json={"payment": {"id": "pay_1", "status": "captured"}},
        status=200,
    )
    responses.add(
        responses.POST,
        "http://payments.test/payments/pay_1/refund",
        json={"status": "refunded", "refund": {"id": "re_1"}},
        status=200,
    )
    client = PaymentServiceClient(config=config)
    capture = client.capture_payment(
        event_id=10,
        attendee_email="person@example.com",
        amount=25.0,
        currency="EUR",
    )
    assert capture["payment"]["status"] == "captured"
    refund = client.refund_payment("pay_1")
    assert refund["status"] == "refunded"
    assert refund["refund"]["id"] == "re_1"


@responses.activate
def test_calendar_service_sync() -> None:
    config = _service_config("calendar_service", "http://calendar.test")
    responses.add(
        responses.POST,
        "http://calendar.test/calendars/sync",
        json={"status": "ok"},
        status=200,
    )
    client = CalendarServiceClient(config=config)
    payload = {"event": {"id": 1}, "ics": "BEGIN:VCALENDAR", "webhooks": []}
    response = client.sync_event(payload)
    assert response["status"] == "ok"


@responses.activate
def test_email_service_send_notification() -> None:
    config = _service_config("email_service", "http://email.test")
    responses.add(
        responses.POST,
        "http://email.test/notifications/send",
        json={"status": "queued"},
        status=200,
    )
    client = EmailServiceClient(config=config)
    response = client.send_notification({"to": "user@example.com", "template": "welcome"})
    assert response["status"] == "queued"


@responses.activate
def test_social_service_publish_event() -> None:
    config = _service_config("social_service", "http://social.test")
    responses.add(
        responses.POST,
        "http://social.test/shares/event",
        json={"status": "shared"},
        status=200,
    )
    client = SocialServiceClient(config=config)
    response = client.publish_event({"event_id": 1, "title": "Launch", "url": "https://example.com"})
    assert response["status"] == "shared"


def test_matching_service_client() -> None:
    payloads: Dict[str, Any] = {}

    def fake_unary_unary(method, request_serializer=None, response_deserializer=None):
        def _call(request, timeout=None):
            payloads["method"] = method
            payloads["request"] = request
            payloads["serialized"] = json.loads(request_serializer(request).decode("utf-8"))
            response = json.dumps({"matches": [{"id": "match-1"}]}).encode("utf-8")
            return response_deserializer(response)

        return _call

    config = ServiceConfig(
        name="matching_service",
        base_url="localhost:50051",
        protocol="grpc",
        timeout=1.0,
        resilience=ResilienceConfig(),
    )

    class FakeChannel:
        def unary_unary(self, method, request_serializer=None, response_deserializer=None):
            return fake_unary_unary(
                method,
                request_serializer=request_serializer,
                response_deserializer=response_deserializer,
            )

    client = MatchingServiceClient(config=config, channel=FakeChannel())
    response = client.find_matches_for_event(99, limit=2)
    assert response["matches"][0]["id"] == "match-1"
    assert payloads["method"] == "/matching.MatchService/FindMatches"
    assert payloads["serialized"]["event_id"] == 99
    assert payloads["serialized"]["limit"] == 2
