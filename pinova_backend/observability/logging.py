"""Logging JSON structuré — production."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class PinovaJsonFormatter(logging.Formatter):
    """Une ligne JSON par record (Render / Loki / CloudWatch friendly)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        for key in (
            'event',
            'request_id',
            'user_id',
            'path',
            'method',
            'latency_ms',
            'status',
        ):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def build_logging_config(*, debug: bool) -> dict:
    if debug:
        return {
            'version': 1,
            'disable_existing_loggers': False,
            'handlers': {
                'console': {'class': 'logging.StreamHandler'},
            },
            'loggers': _pinova_loggers('console'),
        }

    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'json': {
                '()': 'pinova_backend.observability.logging.PinovaJsonFormatter',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'json',
            },
        },
        'loggers': _pinova_loggers('console'),
    }


def _pinova_loggers(handler: str) -> dict:
    names = (
        'pinova.access',
        'pinova.cache',
        'pinova.celery',
        'pinova.resilience',
        'pinova.sentry',
        'pinova.fedapay.webhook',
        'pinova.analytics',
    )
    return {
        name: {
            'handlers': [handler],
            'level': 'INFO',
            'propagate': False,
        }
        for name in names
    }


def log_http_access(
    *,
    request_id: str,
    user_id: int | None,
    path: str,
    method: str,
    latency_ms: float,
    status: int,
) -> None:
    logger = logging.getLogger('pinova.access')
    logger.info(
        'http_request',
        extra={
            'event': 'http_request',
            'request_id': request_id,
            'user_id': user_id,
            'path': path,
            'method': method,
            'latency_ms': round(latency_ms, 2),
            'status': status,
        },
    )
