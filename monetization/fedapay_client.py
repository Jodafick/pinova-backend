"""Client FedaPay partagé (boost, pourboires, etc.)."""

from __future__ import annotations

import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


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
        create_resp = requests.post(
            f'{fedapay_base_url()}/transactions',
            json=payload,
            headers=headers,
            timeout=30,
        )
        if create_resp.status_code >= 400:
            logger.error('FedaPay create failed: %s', create_resp.text)
            return {'error': 'FedaPay transaction create failed'}
        body = create_resp.json()
        tx_id = extract_tx_id(body)
        if not tx_id:
            return {'error': 'Invalid FedaPay response'}
        token_resp = requests.post(
            f'{fedapay_base_url()}/transactions/{tx_id}/token',
            headers=headers,
            timeout=30,
        )
        checkout_url = None
        if token_resp.status_code < 400:
            checkout_url = extract_checkout_url(token_resp.json())
        return {'transaction_id': tx_id, 'checkout_url': checkout_url}
    except requests.RequestException as exc:
        logger.exception('FedaPay request failed: %s', exc)
        return {'error': 'FedaPay unavailable'}


def payments_sandbox_allowed() -> bool:
    return settings.DEBUG or os.environ.get('BOOST_SANDBOX_ACTIVATE', '').lower() == 'true'
