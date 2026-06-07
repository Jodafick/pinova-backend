"""Client FedaPay partagé (boost, pourboires, abonnements) — retry + circuit breaker."""

from __future__ import annotations

import logging
import os
import time

import requests
from django.conf import settings

from pinova_backend.security.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    ExternalRetryableError,
    external_call,
)

logger = logging.getLogger(__name__)

FEDAPAY_CIRCUIT = CircuitBreaker('fedapay', failure_threshold=5, recovery_timeout=60.0)

__all__ = [
    'CircuitOpenError',
    'FEDAPAY_CIRCUIT',
    'create_fedapay_checkout',
    'extract_checkout_url',
    'extract_tx_id',
    'fedapay_base_url',
    'fedapay_get',
    'fedapay_headers',
    'fedapay_health_ping',
    'fedapay_post',
    'payments_sandbox_allowed',
]


def fedapay_base_url() -> str:
    env = os.environ.get('FEDAPAY_ENV', 'sandbox').strip().lower()
    if env == 'live':
        return 'https://api.fedapay.com/v1'
    return 'https://sandbox-api.fedapay.com/v1'


def fedapay_headers() -> dict | None:
    secret = os.environ.get('FEDAPAY_SECRET_KEY', '').strip()
    if not secret:
        return None
    return {
        'Authorization': f'Bearer {secret}',
        'Content-Type': 'application/json',
    }


def _retryable_http_status(status_code: int) -> bool:
    return status_code >= 500 or status_code == 429


def _request(method: str, path: str, *, json=None, timeout: float = 20) -> requests.Response:
    headers = fedapay_headers()
    if not headers:
        raise ValueError('FedaPay is not configured')
    url = f'{fedapay_base_url()}{path}'

    def _do() -> requests.Response:
        resp = requests.request(method, url, json=json, headers=headers, timeout=timeout)
        if _retryable_http_status(resp.status_code):
            raise ExternalRetryableError(f'FedaPay HTTP {resp.status_code}')
        return resp

    return external_call(
        service='fedapay',
        operation=f'{method} {path}',
        fn=_do,
        circuit=FEDAPAY_CIRCUIT,
        max_attempts=4,
    )


def fedapay_post(path: str, *, json=None, timeout: float = 20) -> requests.Response:
    return _request('POST', path, json=json, timeout=timeout)


def fedapay_get(path: str, *, timeout: float = 25) -> requests.Response:
    return _request('GET', path, timeout=timeout)


def fedapay_health_ping() -> tuple[bool, str, float | None]:
    """
    Ping léger FedaPay pour health check (sans retry / circuit).
    Retourne (ok, detail, latency_ms).
    """
    headers = fedapay_headers()
    if not headers:
        return True, 'skipped_no_secret', None
    if FEDAPAY_CIRCUIT.is_open():
        return False, 'circuit_open', None
    started = time.perf_counter()
    try:
        url = f'{fedapay_base_url()}/events'
        resp = requests.get(url, headers=headers, params={'page': 1, 'per_page': 1}, timeout=5)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if resp.status_code < 500:
            return True, f'http_{resp.status_code}', latency_ms
        return False, f'http_{resp.status_code}', latency_ms
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return False, str(exc)[:200], latency_ms


def extract_tx_id(payload) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get('id'):
        return str(payload.get('id'))
    for key in ('transaction', 'data', 'v1/transaction'):
        nested = payload.get(key)
        if isinstance(nested, dict) and nested.get('id'):
            return str(nested.get('id'))
    return None


def extract_checkout_url(payload) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ('url', 'payment_url', 'redirect_url'):
        if payload.get(key):
            return payload.get(key)
    for key in ('token', 'data'):
        nested = payload.get(key)
        if isinstance(nested, dict):
            for nk in ('url', 'payment_url', 'redirect_url'):
                if nested.get(nk):
                    return nested.get(nk)
    return None


def create_fedapay_checkout(
    *,
    request,
    description: str,
    amount: int,
    currency_iso: str,
    callback_url: str | None = None,
) -> dict:
    headers = fedapay_headers()
    if not headers:
        return {'error': 'FedaPay is not configured'}
    default_callback = f"{str(settings.FRONTEND_URL).rstrip('/')}/"
    callback = callback_url or os.environ.get('FEDAPAY_CALLBACK_URL') or default_callback
    payload = {
        'description': description[:500],
        'amount': int(amount),
        'currency': {'iso': currency_iso},
        'callback_url': callback,
        'customer': {
            'email': request.user.email or f'{request.user.username}@pinova.local',
            'firstname': request.user.username[:50],
            'lastname': 'Pinova',
        },
    }
    try:
        create_resp = fedapay_post('/transactions', json=payload, timeout=30)
        if create_resp.status_code >= 400:
            logger.error('FedaPay create failed: %s', create_resp.text)
            return {'error': 'FedaPay transaction create failed'}
        body = create_resp.json()
        tx_id = extract_tx_id(body)
        if not tx_id:
            return {'error': 'Invalid FedaPay response'}
        token_resp = fedapay_post(f'/transactions/{tx_id}/token', timeout=30)
        checkout_url = None
        if token_resp.status_code < 400:
            checkout_url = extract_checkout_url(token_resp.json())
        return {'transaction_id': tx_id, 'checkout_url': checkout_url}
    except CircuitOpenError:
        return {'error': 'FedaPay temporarily unavailable (circuit open)'}
    except requests.RequestException as exc:
        logger.exception('FedaPay request failed: %s', exc)
        return {'error': 'FedaPay unavailable'}


def payments_sandbox_allowed() -> bool:
    return settings.DEBUG or os.environ.get('BOOST_SANDBOX_ACTIVATE', '').lower() == 'true'
