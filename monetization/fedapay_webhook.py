"""Webhook FedaPay — validation, idempotence, journalisation structurée."""

from __future__ import annotations

import hmac
import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response

from .models import WebhookEventProcessed

logger = logging.getLogger('pinova.fedapay.webhook')

APPROVED_STATUSES = frozenset({'approved', 'success', 'successful', 'completed'})
FAILED_STATUSES = frozenset({'failed', 'declined', 'rejected'})
CANCELED_STATUSES = frozenset({'canceled', 'cancelled'})


def get_fedapay_webhook_secret() -> str:
    secret = (getattr(settings, 'FEDAPAY_WEBHOOK_SECRET', None) or '').strip()
    if not secret and not settings.DEBUG:
        raise ImproperlyConfigured(
            'FEDAPAY_WEBHOOK_SECRET est obligatoire en production (DEBUG=False). '
            'Configurez un secret fort et unique dans les variables d’environnement.'
        )
    return secret


def normalize_transaction_body(body: dict | None) -> dict:
    if not isinstance(body, dict):
        return {}
    data = body.get('data')
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if isinstance(data, dict):
        markers = ('status', 'id', 'amount', 'approved_at', 'reference', 'receipt_url')
        if any(k in data for k in markers):
            return data
    for key in ('v1/transaction', 'transaction'):
        nested = body.get(key)
        if isinstance(nested, dict) and any(k in nested for k in ('status', 'id', 'amount', 'approved_at')):
            return nested
    return body


def normalized_status(normalized: dict | None) -> str:
    s = str((normalized or {}).get('status') or '').strip().lower()
    if s:
        return s
    if (normalized or {}).get('approved_at'):
        return 'approved'
    return ''


def webhook_transaction_id(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ''
    tid = str(payload.get('transaction_id') or payload.get('id') or '').strip()
    if tid:
        return tid
    for key in ('data', 'v1/transaction', 'transaction', 'entity'):
        block = payload.get(key)
        if isinstance(block, dict):
            tid = str(block.get('id') or block.get('transaction_id') or '').strip()
            if tid:
                return tid
        elif isinstance(block, list) and block and isinstance(block[0], dict):
            tid = str(block[0].get('id') or block[0].get('transaction_id') or '').strip()
            if tid:
                return tid
    return ''


def webhook_status(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ''
    direct = str(payload.get('status') or '').strip().lower()
    if direct:
        return direct
    for key in ('data', 'v1/transaction', 'transaction', 'entity'):
        block = payload.get(key)
        if isinstance(block, dict):
            st = normalized_status(block)
            if st:
                return st
        elif isinstance(block, list) and block and isinstance(block[0], dict):
            st = normalized_status(block[0])
            if st:
                return st
    return ''


def webhook_amount(payload: dict | None) -> int | None:
    normalized = normalize_transaction_body(payload if isinstance(payload, dict) else {})
    raw = normalized.get('amount')
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def extract_webhook_token(request) -> str:
    return str(
        request.headers.get('X-Webhook-Token')
        or request.headers.get('X-Fedapay-Webhook-Token')
        or request.data.get('webhook_token')
        or ''
    ).strip()


def validate_webhook_secret(request) -> Response | None:
    expected = get_fedapay_webhook_secret()
    provided = extract_webhook_token(request)
    if not expected:
        if settings.DEBUG and not provided:
            return None
        if not provided:
            return Response({'error': 'Webhook secret required'}, status=status.HTTP_403_FORBIDDEN)
    elif not hmac.compare_digest(provided, expected):
        log_webhook_event(
            flow='unknown',
            status='rejected',
            transaction_id=webhook_transaction_id(dict(request.data)) or None,
            user_id=None,
            amount=None,
            extra={'reason': 'invalid_secret'},
        )
        return Response({'error': 'Invalid webhook token'}, status=status.HTTP_403_FORBIDDEN)
    return None


def log_webhook_event(
    *,
    flow: str,
    status: str,
    transaction_id: str | None,
    user_id: int | None,
    amount: int | None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        'event': 'fedapay_webhook',
        'flow': flow,
        'status': status,
        'transaction_id': transaction_id,
        'user_id': user_id,
        'amount': amount,
        **(extra or {}),
    }
    logger.info('fedapay_webhook %s', payload)

    failure_statuses = FAILED_STATUSES | CANCELED_STATUSES | frozenset({'rejected', 'amount_mismatch', 'error'})
    if status in failure_statuses or (extra or {}).get('reason') in ('invalid_secret', 'amount_mismatch'):
        try:
            from pinova_backend.observability.sentry import capture_fedapay_webhook_failure

            capture_fedapay_webhook_failure(
                flow=flow,
                status=status,
                transaction_id=transaction_id,
                user_id=user_id,
                amount=amount,
                extra=extra,
            )
        except Exception:
            logger.debug('Sentry FedaPay webhook capture skipped', exc_info=True)


def is_webhook_replay(transaction_id: str, event_type: str) -> bool:
    return WebhookEventProcessed.objects.filter(
        transaction_id=transaction_id,
        event_type=event_type,
    ).exists()


def mark_webhook_processed(transaction_id: str, event_type: str) -> bool:
    """Retourne True si enregistré, False si rejeu concurrent."""
    try:
        with transaction.atomic():
            WebhookEventProcessed.objects.create(
                transaction_id=transaction_id,
                event_type=event_type,
            )
        return True
    except IntegrityError:
        return False


def claim_webhook_event(transaction_id: str, event_type: str) -> tuple[bool, WebhookEventProcessed | None]:
    """Retourne (created, row). created=False => rejeu."""
    if is_webhook_replay(transaction_id, event_type):
        row = WebhookEventProcessed.objects.filter(
            transaction_id=transaction_id,
            event_type=event_type,
        ).first()
        return False, row
    if mark_webhook_processed(transaction_id, event_type):
        row = WebhookEventProcessed.objects.filter(
            transaction_id=transaction_id,
            event_type=event_type,
        ).first()
        return True, row
    row = WebhookEventProcessed.objects.filter(
        transaction_id=transaction_id,
        event_type=event_type,
    ).first()
    return False, row


def amounts_match(expected: int, webhook_amount_value: int | None) -> bool:
    if webhook_amount_value is None:
        return True
    return int(expected) == int(webhook_amount_value)


def replay_response(flow: str, transaction_id: str, event_type: str) -> Response:
    log_webhook_event(
        flow=flow,
        status='replay_skipped',
        transaction_id=transaction_id,
        user_id=None,
        amount=None,
        extra={'event_type': event_type},
    )
    return Response(
        {'status': 'already_processed', 'skipped': True, 'flow': flow},
        status=status.HTTP_200_OK,
    )


def amount_mismatch_response(
    *,
    flow: str,
    transaction_id: str,
    user_id: int | None,
    expected: int,
    received: int | None,
) -> Response:
    log_webhook_event(
        flow=flow,
        status='amount_mismatch',
        transaction_id=transaction_id,
        user_id=user_id,
        amount=received,
        extra={'expected_amount': expected},
    )
    return Response(
        {
            'status': 'amount_mismatch',
            'skipped': True,
            'flow': flow,
        },
        status=status.HTTP_200_OK,
    )
