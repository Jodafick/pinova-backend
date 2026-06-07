"""Analytics serveur — PostHog EU cloud (événements revenue / onboarding fiables)."""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger('pinova.analytics')

_posthog = None
_initialized = False


def _ensure_posthog():
    global _posthog, _initialized
    if _initialized:
        return _posthog
    _initialized = True
    api_key = (getattr(settings, 'POSTHOG_API_KEY', '') or '').strip()
    if not api_key:
        return None
    try:
        import posthog

        posthog.project_api_key = api_key
        posthog.host = (getattr(settings, 'POSTHOG_HOST', '') or 'https://eu.i.posthog.com').rstrip('/')
        posthog.sync_mode = True
        _posthog = posthog
    except ImportError:
        logger.debug('posthog package absent — analytics serveur désactivé')
        _posthog = None
    return _posthog


def capture_event(
    distinct_id: str | int,
    event: str,
    *,
    properties: dict[str, Any] | None = None,
) -> bool:
    """Envoie un événement PostHog (no-op si clé absente)."""
    ph = _ensure_posthog()
    if not ph:
        return False
    try:
        ph.capture(
            distinct_id=str(distinct_id),
            event=event,
            properties={'platform': 'backend', **(properties or {})},
        )
        return True
    except Exception:
        logger.debug('PostHog capture failed event=%s', event, exc_info=True)
        return False


def _minor_to_major_amount(amount: int | None, currency: str) -> float | None:
    if amount is None:
        return None
    # Montants stockés en unités mineures (centimes XOF, centimes EUR, etc.)
    if currency.upper() in {'XOF', 'XAF', 'JPY', 'KRW'}:
        return round(amount, 2)
    return round(amount / 100.0, 2)


def _revenue_props(
    *,
    flow: str,
    amount: int | None,
    currency: str,
    transaction_id: str | None,
) -> dict[str, Any]:
    major = _minor_to_major_amount(amount, currency)
    props: dict[str, Any] = {
        'flow': flow,
        'currency': currency,
        'revenue_source': 'fedapay_webhook',
        'tracking_role': 'revenue',
    }
    if amount is not None:
        props['amount_minor'] = amount
        props['amount'] = amount
    if transaction_id:
        props['transaction_id'] = transaction_id
    if major is not None:
        props['$revenue'] = major
        props['$currency'] = currency
    return props


def capture_revenue_recorded(
    *,
    user_id: int,
    flow: str,
    amount: int | None,
    currency: str = 'XOF',
    transaction_id: str | None = None,
) -> bool:
    """Événement revenue authoritative — webhook FedaPay approuvé."""
    return capture_event(
        user_id,
        'revenue_recorded',
        properties=_revenue_props(
            flow=flow,
            amount=amount,
            currency=currency,
            transaction_id=transaction_id,
        ),
    )


def capture_checkout_success(
    *,
    user_id: int,
    flow: str,
    amount: int | None,
    currency: str = 'XOF',
    transaction_id: str | None = None,
) -> bool:
    props = _revenue_props(
        flow=flow,
        amount=amount,
        currency=currency,
        transaction_id=transaction_id,
    )
    capture_revenue_recorded(
        user_id=user_id,
        flow=flow,
        amount=amount,
        currency=currency,
        transaction_id=transaction_id,
    )
    return capture_event(user_id, 'checkout_success', properties=props)


def capture_referral_link_opened(
    *,
    distinct_id: str,
    ref_code: str,
    referrer_id: int | None = None,
) -> bool:
    props: dict[str, Any] = {'ref_code': ref_code, 'referral_source': 'link'}
    if referrer_id is not None:
        props['referrer_id'] = referrer_id
    return capture_event(distinct_id, 'referral_link_opened', properties=props)


def capture_register_with_ref_code(
    *,
    user_id: int,
    ref_code: str,
    signup_channel: str = 'referral',
) -> bool:
    return capture_event(
        user_id,
        'register_with_ref_code',
        properties={
            'ref_code': ref_code,
            'signup_channel': signup_channel,
            'has_ref_code': True,
        },
    )


def capture_boost_purchased(*, user_id: int, amount: int | None, pin_id: int | None = None) -> bool:
    props: dict[str, Any] = {}
    if amount is not None:
        props['amount'] = amount
    if pin_id is not None:
        props['pin_id'] = pin_id
    return capture_event(user_id, 'boost_purchased', properties=props)


def capture_tip_sent(*, sender_id: int, amount: int | None, recipient_id: int | None = None) -> bool:
    props: dict[str, Any] = {}
    if amount is not None:
        props['amount'] = amount
    if recipient_id is not None:
        props['recipient_id'] = recipient_id
    return capture_event(sender_id, 'tip_sent', properties=props)


def capture_campaign_launched(*, user_id: int, campaign_id: int, amount: int | None = None) -> bool:
    props: dict[str, Any] = {'campaign_id': campaign_id}
    if amount is not None:
        props['amount'] = amount
    return capture_event(user_id, 'campaign_launched', properties=props)
