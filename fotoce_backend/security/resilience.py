"""
Résilience appels services externes — retry (tenacity), circuit breaker, logs JSON structurés.

Champs log `event=external_service` : service, operation, latency_ms, attempt, outcome.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, TypeVar

from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger('fotoce.resilience')

T = TypeVar('T')


class CircuitOpenError(Exception):
    """Circuit breaker ouvert — appels bloqués temporairement."""


class ExternalRetryableError(Exception):
    """Erreur transitoire — éligible au retry."""


def log_external_call(
    *,
    service: str,
    operation: str,
    latency_ms: float,
    attempt: int,
    outcome: str,
    **extra: Any,
) -> None:
    payload = {
        'event': 'external_service',
        'service': service,
        'operation': operation,
        'latency_ms': round(float(latency_ms), 2),
        'attempt': int(attempt),
        'outcome': outcome,
    }
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    logger.info(json.dumps(payload, ensure_ascii=False))


@dataclass
class CircuitBreaker:
    """
    Circuit breaker simple : ouvert après `failure_threshold` échecs consécutifs,
    refermé après `recovery_timeout` secondes.
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    _failure_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._reset_locked()
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._reset_locked()

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._opened_at = time.monotonic()

    def _reset_locked(self) -> None:
        self._failure_count = 0
        self._opened_at = None


def external_call(
    *,
    service: str,
    operation: str,
    fn: Callable[[], T],
    circuit: CircuitBreaker | None = None,
    max_attempts: int = 4,
    min_wait: float = 0.5,
    max_wait: float = 30.0,
) -> T:
    """
    Exécute `fn` avec retry exponentiel (tenacity) et circuit breaker optionnel.
    `max_attempts` = nombre total de tentatives (ex. 4 = 1 initiale + 3 retries).
    """
    if circuit is not None and circuit.is_open():
        log_external_call(
            service=service,
            operation=operation,
            latency_ms=0,
            attempt=0,
            outcome='circuit_open',
            circuit=circuit.name,
        )
        raise CircuitOpenError(f'{service} circuit open')

    last_error: Exception | None = None

    for attempt_state in Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(ExternalRetryableError),
        reraise=True,
    ):
        with attempt_state:
            attempt = attempt_state.retry_state.attempt_number
            if circuit is not None and circuit.is_open():
                log_external_call(
                    service=service,
                    operation=operation,
                    latency_ms=0,
                    attempt=attempt,
                    outcome='circuit_open',
                    circuit=circuit.name,
                )
                raise CircuitOpenError(f'{service} circuit open')

            start = time.perf_counter()
            try:
                result = fn()
                latency_ms = (time.perf_counter() - start) * 1000
                if circuit is not None:
                    circuit.record_success()
                log_external_call(
                    service=service,
                    operation=operation,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    outcome='success',
                )
                return result
            except CircuitOpenError:
                raise
            except ExternalRetryableError as exc:
                last_error = exc
                latency_ms = (time.perf_counter() - start) * 1000
                if circuit is not None:
                    circuit.record_failure()
                will_retry = attempt < max_attempts
                log_external_call(
                    service=service,
                    operation=operation,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    outcome='retry' if will_retry else 'failure',
                    error=str(exc)[:200],
                )
                raise
            except Exception as exc:
                last_error = exc
                latency_ms = (time.perf_counter() - start) * 1000
                if circuit is not None:
                    circuit.record_failure()
                log_external_call(
                    service=service,
                    operation=operation,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    outcome='failure',
                    error=str(exc)[:200],
                )
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError('external_call ended without result')  # pragma: no cover


def retry_external(
    *,
    service: str,
    operation: str,
    circuit: CircuitBreaker | None = None,
    max_attempts: int = 4,
):
    """Décorateur — même sémantique que `external_call`."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            return external_call(
                service=service,
                operation=operation,
                fn=lambda: fn(*args, **kwargs),
                circuit=circuit,
                max_attempts=max_attempts,
            )

        return wrapper

    return decorator
