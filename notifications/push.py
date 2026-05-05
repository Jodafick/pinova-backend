import json
import logging
import os
from urllib.parse import quote

import requests
from pywebpush import WebPushException, webpush

from .models import ExpoPushToken, PushSubscription

logger = logging.getLogger(__name__)

EXPO_PUSH_API_URL = 'https://exp.host/--/api/v2/push/send'
EXPO_CHUNK_SIZE = 90


def _push_action_url(notification):
    """URL de navigation lorsque notification.action_url est vide (ex. like / comment)."""
    au = (getattr(notification, 'action_url', None) or '').strip()
    if au:
        return au
    meta = getattr(notification, 'metadata', None) if notification else None
    if not isinstance(meta, dict):
        meta = {}
    slug = getattr(notification, 'pin_slug', None)
    if slug and meta.get('is_story'):
        return f"/?story={quote(str(slug), safe='')}"
    if slug:
        return f'/pin/{slug}'
    return '/'


def get_vapid_public_key():
    return os.environ.get('WEB_PUSH_VAPID_PUBLIC_KEY', '').strip()


def is_push_configured():
    return bool(
        os.environ.get('WEB_PUSH_VAPID_PRIVATE_KEY', '').strip()
        and os.environ.get('WEB_PUSH_VAPID_PUBLIC_KEY', '').strip()
        and os.environ.get('WEB_PUSH_VAPID_CLAIMS_SUB', '').strip()
    )


def _notification_payload_dict(notification):
    return {
        'title': notification.title or 'PINOVA',
        'body': notification.message,
        'notification_type': notification.notification_type,
        'action_url': _push_action_url(notification),
        'notification_id': notification.id,
    }


def _send_web_push_for_user(recipient_user, payload_dict):
    if not is_push_configured():
        return
    subscriptions = PushSubscription.objects.filter(user=recipient_user, is_active=True)
    if not subscriptions.exists():
        return

    payload = json.dumps(payload_dict)
    vapid_private_key = os.environ.get('WEB_PUSH_VAPID_PRIVATE_KEY', '').strip()
    vapid_claims = {'sub': os.environ.get('WEB_PUSH_VAPID_CLAIMS_SUB', '').strip()}

    for sub in subscriptions:
        subscription_info = {
            'endpoint': sub.endpoint,
            'keys': {
                'p256dh': sub.p256dh,
                'auth': sub.auth,
            },
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
            )
        except WebPushException as exc:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status_code in {404, 410}:
                sub.is_active = False
                sub.save(update_fields=['is_active', 'updated_at'])


def _expo_serializable_data(payload_dict):
    out = {}
    for k, v in payload_dict.items():
        out[k] = '' if v is None else str(v)
    return out


def _deactivate_dead_expo_tokens(tokens, expo_response_payload):
    data = expo_response_payload.get('data') if isinstance(expo_response_payload, dict) else None
    if not isinstance(data, list) or len(data) != len(tokens):
        return
    stale_errors = frozenset({'DeviceNotRegistered', 'InvalidCredentials'})
    for item, tok in zip(data, tokens):
        if not isinstance(item, dict) or item.get('status') == 'ok':
            continue
        details = item.get('details') or {}
        code = ''
        if isinstance(details, dict):
            code = str(details.get('error') or '').strip()
        msg = str(item.get('message') or '').lower()
        if code in stale_errors or 'devicenotregistered' in msg.replace(' ', ''):
            ExpoPushToken.objects.filter(token=tok).update(is_active=False)


def _send_expo_push_chunk(tokens, payload_dict):
    expo_access = os.environ.get('EXPO_ACCESS_TOKEN', '').strip()
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    if expo_access:
        headers['Authorization'] = f'Bearer {expo_access}'

    data_payload = _expo_serializable_data(payload_dict)
    messages = [
        {
            'to': tok,
            'title': str(payload_dict.get('title') or 'PINOVA'),
            'body': str(payload_dict.get('body') or ''),
            'sound': 'default',
            'priority': 'high',
            'channelId': 'default',
            'data': data_payload,
        }
        for tok in tokens
    ]

    try:
        resp = requests.post(EXPO_PUSH_API_URL, json=messages, headers=headers, timeout=25)
        resp.raise_for_status()
        _deactivate_dead_expo_tokens(tokens, resp.json())
    except requests.RequestException as exc:
        logger.warning('Expo push send failed: %s', exc)


def _send_expo_mobile_for_user(recipient_user, payload_dict):
    token_list = list(
        ExpoPushToken.objects.filter(user=recipient_user, is_active=True).values_list('token', flat=True),
    )
    if not token_list:
        return
    for i in range(0, len(token_list), EXPO_CHUNK_SIZE):
        chunk = token_list[i : i + EXPO_CHUNK_SIZE]
        _send_expo_push_chunk(chunk, payload_dict)


def send_notification_push(notification):
    """
    Envoi Web Push (PWA — VAPID) + Expo Push (applications mobiles).
    Chaque canal est traité indépendamment selon les abonnements actifs du destinataire.
    """
    payload_dict = _notification_payload_dict(notification)
    recipient_user = notification.recipient
    _send_web_push_for_user(recipient_user, payload_dict)
    _send_expo_mobile_for_user(recipient_user, payload_dict)
