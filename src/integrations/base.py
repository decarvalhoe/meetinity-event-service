"""Base utilities shared by integration clients."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol

import requests

try:  # pragma: no cover - optional dependency for gRPC
    import grpc  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for offline tests
    grpc = None  # type: ignore

from src.config import ResilienceConfig, ServiceConfig, get_service_config


class IntegrationError(RuntimeError):
    """Raised when a downstream call fails irrecoverably."""


class CircuitOpenError(IntegrationError):
    """Raised when the circuit breaker prevents further calls."""


@dataclass
class _CircuitBreakerState:
    failures: int = 0
    open_until: float = 0.0


class CircuitBreaker:
    """Minimal circuit breaker implementation."""

    def __init__(self, config: ResilienceConfig) -> None:
        self.config = config
        self.state = _CircuitBreakerState()

    def allow(self) -> None:
        now = time.monotonic()
        if self.state.open_until and now < self.state.open_until:
            raise CircuitOpenError("Circuit breaker is open; skipping call.")
        if self.state.open_until and now >= self.state.open_until:
            self.state = _CircuitBreakerState()

    def record_success(self) -> None:
        self.state = _CircuitBreakerState()

    def record_failure(self) -> None:
        self.state.failures += 1
        if self.state.failures >= self.config.circuit_breaker_failure_threshold:
            self.state.open_until = (
                time.monotonic() + self.config.circuit_breaker_reset_timeout
            )


class Retryable(Protocol):
    def __call__(self) -> Any:  # pragma: no cover - typing protocol
        ...


class IntegrationClient:
    """Base class wrapping retry and circuit breaker semantics."""

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.breaker = CircuitBreaker(config.resilience)

    def _execute(self, operation: Retryable) -> Any:
        attempts = 0
        delay = self.config.resilience.backoff_factor
        max_attempts = max(1, self.config.resilience.max_attempts)
        max_backoff = max(delay, self.config.resilience.max_backoff)

        while True:
            self.breaker.allow()
            try:
                result = operation()
            except CircuitOpenError:
                raise
            except Exception as exc:  # pragma: no cover - generic fallback
                self.breaker.record_failure()
                attempts += 1
                if attempts >= max_attempts:
                    raise IntegrationError(str(exc)) from exc
                time.sleep(delay)
                delay = min(delay * 2, max_backoff)
            else:
                self.breaker.record_success()
                return result


class HttpClient(IntegrationClient):
    """HTTP client with retry/backoff semantics."""

    def __init__(self, config: ServiceConfig, session: Optional[requests.Session] = None) -> None:
        super().__init__(config)
        self.session = session or requests.Session()

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.secret:
            headers["Authorization"] = f"Bearer {self.config.secret}"
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = self._build_url(path)

        def _call() -> Dict[str, Any]:
            response = self.session.request(
                method,
                url,
                json=json_payload,
                params=params,
                headers=self._headers(headers),
                timeout=self.config.timeout,
            )
            if response.status_code >= 400:
                raise IntegrationError(
                    f"HTTP {response.status_code} error calling {url}: {response.text}"
                )
            if not response.content:
                return {}
            try:
                return response.json()
            except json.JSONDecodeError:
                raise IntegrationError(
                    f"Invalid JSON payload received from {url}: {response.text}"
                )

        return self._execute(_call)

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        base = self.config.base_url.rstrip("/")
        suffix = path.lstrip("/")
        return f"{base}/{suffix}"


class GrpcClient(IntegrationClient):
    """Simple gRPC client wrapper."""

    def __init__(self, config: ServiceConfig, channel: Optional[Any] = None) -> None:
        if grpc is None:  # pragma: no cover - optional dependency
            raise RuntimeError("grpcio is required for gRPC integrations")
        super().__init__(config)
        target = config.base_url
        self.channel = channel or grpc.insecure_channel(target)

    def call_unary_unary(
        self,
        method: str,
        request: Any,
        *,
        request_serializer: Callable[[Any], bytes],
        response_deserializer: Callable[[bytes], Any],
    ) -> Any:
        def _call() -> Any:
            stub = self.channel.unary_unary(
                method,
                request_serializer=request_serializer,
                response_deserializer=response_deserializer,
            )
            return stub(request, timeout=self.config.timeout)

        return self._execute(_call)


def build_http_client(service_name: str, session: Optional[requests.Session] = None) -> HttpClient:
    config = get_service_config(service_name)
    return HttpClient(config, session=session)


def build_grpc_client(service_name: str, channel: Optional[Any] = None) -> GrpcClient:
    config = get_service_config(service_name)
    return GrpcClient(config, channel=channel)

