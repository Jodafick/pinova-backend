"""Configuration Sentry — Django + scrub données sensibles."""
from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings

logger = logging.getLogger('fotoce.sentry')

_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
_JWT_RE = re.compile(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')
_BEARER_RE = re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.I)
_SENSITIVE_KEY = re.compile(r'token|password|secret|authorization|cookie|refresh|access|otp|api[_-]?key', re.I)
_REDACTED = '[Filtered]'

_initialized = False


def _scrub_string(value: str) -> str:
    value = _JWT_RE.sub(_REDACTED, value)
    value = _BEARER_RE.sub(f'Bearer {_REDACTED}', value)
    return _EMAIL_RE.sub(_REDACTED, value)


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    if isinstance(value, dict):
        return _scrub_mapping(value)
    return value


def _scrub_mapping(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in data.items():
        if _SENSITIVE_KEY.search(str(key)):
            out[key] = _REDACTED
        else:
            out[key] = _scrub_value(val)
    return out


def scrub_sentry_event(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    del hint
    if 'request' in event and isinstance(event['request'], dict):
        event['request'] = _scrub_mapping(event['request'])
    if 'extra' in event and isinstance(event['extra'], dict):
        event['extra'] = _scrub_mapping(event['extra'])
    user = event.get('user')
    if isinstance(user, dict) and 'email' in user:
        user = dict(user)
        user['email'] = _REDACTED
        event['user'] = user
    breadcrumbs = event.get('breadcrumbs')
    if isinstance(breadcrumbs, list):
        for crumb in breadcrumbs:
            if not isinstance(crumb, dict):
                continue
            if isinstance(crumb.get('message'), str):
                crumb['message'] = _scrub_string(crumb['message'])
            if isinstance(crumb.get('data'), dict):
                crumb['data'] = _scrub_mapping(crumb['data'])
    return event


def init_sentry() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    dsn = (getattr(settings, 'SENTRY_DSN', '') or '').strip()
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.debug('sentry-sdk absent — observabilité Sentry désactivée')
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=getattr(settings, 'SENTRY_ENVIRONMENT', 'development'),
        release=(getattr(settings, 'SENTRY_RELEASE', '') or None),
        integrations=[
            DjangoIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=float(getattr(settings, 'SENTRY_TRACES_SAMPLE_RATE', 0.1)),
        send_default_pii=False,
        before_send=scrub_sentry_event,
    )
    logger.info('Sentry initialisé release=%s', getattr(settings, 'SENTRY_RELEASE', ''))


from fotoce_backend.core.request_context import get_request_id


def _apply_request_id_scope(scope) -> None:
    rid = get_request_id()
    if rid:
        scope.set_tag('request_id', rid)


def capture_fedapay_webhook_failure(
    *,
    flow: str,
    status: str,
    transaction_id: str | None,
    user_id: int | None = None,
    amount: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    dsn = (getattr(settings, 'SENTRY_DSN', '') or '').strip()
    if not dsn:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            _apply_request_id_scope(scope)
            scope.set_tag('fedapay.webhook', 'failure')
            scope.set_tag('fedapay.flow', flow)
            scope.set_tag('fedapay.status', status)
            if transaction_id:
                scope.set_tag('transaction_id', transaction_id)
            if user_id:
                scope.set_user({'id': str(user_id)})
            scope.set_context(
                'fedapay_webhook',
                _scrub_mapping(
                    {
                        'flow': flow,
                        'status': status,
                        'transaction_id': transaction_id,
                        'user_id': user_id,
                        'amount': amount,
                        **(extra or {}),
                    }
                ),
            )
            sentry_sdk.capture_message(
                f'FedaPay webhook failure ({flow}/{status})',
                level='error',
            )
    except Exception:
        logger.debug('Sentry capture FedaPay failure skipped', exc_info=True)


def capture_slow_api(*, method: str, path: str, status_code: int, duration_ms: float) -> None:
    dsn = (getattr(settings, 'SENTRY_DSN', '') or '').strip()
    if not dsn:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            _apply_request_id_scope(scope)
            scope.set_tag('slow_api', 'true')
            scope.set_tag('http.method', method)
            scope.set_context(
                'api_timing',
                {'path': path, 'method': method, 'status_code': status_code, 'duration_ms': round(duration_ms, 2)},
            )
            sentry_sdk.capture_message(
                f'Slow API {method} {path} ({duration_ms:.0f}ms)',
                level='warning',
            )
    except Exception:
        logger.debug('Sentry slow API capture skipped', exc_info=True)
