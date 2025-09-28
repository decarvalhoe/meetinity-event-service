"""Centralised configuration management for integrations and resilience."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Optional


@dataclass(frozen=True)
class ResilienceConfig:
    """Retry and circuit breaker settings for outbound integrations."""

    max_attempts: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 5.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: float = 30.0


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration for a downstream dependency."""

    name: str
    base_url: str
    protocol: str = "http"
    timeout: float = 5.0
    secret: Optional[str] = None
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)


@dataclass(frozen=True)
class AppConfig:
    """Aggregate application configuration."""

    services: Dict[str, ServiceConfig]

    def service(self, name: str) -> ServiceConfig:
        try:
            return self.services[name]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError(f"Unknown service configuration requested: {name}") from exc


def _get_env_name(service_name: str, key: str) -> str:
    return f"{service_name.upper()}_{key.upper()}"


def _load_resilience(service_name: str) -> ResilienceConfig:
    def _get_int(var: str, default: int) -> int:
        value = os.getenv(_get_env_name(service_name, var))
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _get_float(var: str, default: float) -> float:
        value = os.getenv(_get_env_name(service_name, var))
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    return ResilienceConfig(
        max_attempts=_get_int("MAX_ATTEMPTS", 3),
        backoff_factor=_get_float("BACKOFF_FACTOR", 0.5),
        max_backoff=_get_float("MAX_BACKOFF", 5.0),
        circuit_breaker_failure_threshold=_get_int("CB_FAILURE_THRESHOLD", 5),
        circuit_breaker_reset_timeout=_get_float("CB_RESET_TIMEOUT", 30.0),
    )


def _load_service_config(
    service_name: str,
    *,
    default_url: str,
    protocol: str = "http",
    default_timeout: float = 5.0,
) -> ServiceConfig:
    base_url = os.getenv(_get_env_name(service_name, "URL"), default_url)
    timeout = os.getenv(_get_env_name(service_name, "TIMEOUT"))
    secret = os.getenv(_get_env_name(service_name, "SECRET"))
    parsed_timeout = float(timeout) if timeout else default_timeout

    return ServiceConfig(
        name=service_name,
        base_url=base_url,
        protocol=os.getenv(_get_env_name(service_name, "PROTOCOL"), protocol),
        timeout=parsed_timeout,
        secret=secret,
        resilience=_load_resilience(service_name),
    )


@lru_cache()
def get_config() -> AppConfig:
    """Return the lazily initialised application configuration."""

    services = {
        "user_service": _load_service_config(
            "user_service", default_url="http://user-service.local/api"
        ),
        "matching_service": _load_service_config(
            "matching_service", default_url="localhost:50051", protocol="grpc"
        ),
        "payment_service": _load_service_config(
            "payment_service", default_url="http://payment-service.local/api"
        ),
        "calendar_service": _load_service_config(
            "calendar_service", default_url="http://calendar-service.local/api"
        ),
        "email_service": _load_service_config(
            "email_service", default_url="http://email-service.local/api"
        ),
        "social_service": _load_service_config(
            "social_service", default_url="http://social-service.local/api"
        ),
    }
    return AppConfig(services=services)


def get_service_config(service_name: str) -> ServiceConfig:
    """Shortcut to retrieve an individual service configuration."""

    config = get_config()
    return config.service(service_name)

