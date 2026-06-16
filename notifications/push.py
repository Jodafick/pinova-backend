import json
import logging
import os
from urllib.parse import quote

import requests
from pywebpush import WebPushException, webpush

from fotoce_backend.security.resilience import ExternalRetryableError, external_call
from .models import ExpoPushToken, PushSubscription

logger = logging.getLogger(__name__)

EXPO_PUSH_API_URL = 'https://exp.host/--/api/v2/push/send'
EXPO_PUSH_BATCH_SIZE = 100

_EXPO_TOKEN_PREFIX = 'ExponentPushToken['
_EXPO_LOG_BODY_MAX = 16000


def _expo_ticket_from_send_response(body):
    if not isinstance(body, dict):
        return None
    data = body.get('data')
    if isinstance(data, dict) and data.get('status') is not None:
        return data
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    return None


def _expo_tickets_from_batch_response(body):
    if not isinstance(body, dict):
        return []
    data = body.get('data')
    if isinstance(data, list):
        return [t for t in data if isinstance(t, dict)]
    ticket = _expo_ticket_from_send_response(body)
    return [ticket] if ticket else []


def _expo_should_deactivate_token(ticket):
    if not isinstance(ticket, dict) or ticket.get('status') == 'ok':
        return False
    details = ticket.get('details') or {}
    code = ''
    if isinstance(details, dict):
        code = str(details.get('error') or '').strip()
    msg = str(ticket.get('message') or '').lower()
    return code == 'DeviceNotRegistered' or 'devicenotregistered' in msg.replace(' ', '')


def _push_action_url(notification):
    au = (getattr(notification, 'action_url', None) or '').strip()
    if au:
        return au
    meta = getattr(notification, 'metadata', None) if notification else None
    if not isinstance(meta, dict):
        meta = {}
    slug = getattr(notification, 'foto_slug', None)
    if slug and meta.get('is_story'):
        return f"/?story={quote(str(slug), safe='')}"
    if slug:
        return f'/foto/{slug}'
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
    slug = getattr(notification, 'foto_slug', None)
    metadata = getattr(notification, 'metadata', None)
    if not isinstance(metadata, dict):
        metadata = {}
    out = {
        'title': notification.title or 'FOTOCE',
        'body': notification.message,
        'notification_type': notification.notification_type,
        'action_url': _push_action_url(notification),
        'notification_id': notification.id,
        'metadata_json': json.dumps(metadata, ensure_ascii=False, separators=(',', ':')),
    }
    if slug:
        out['foto_slug'] = str(slug)
    cid = getattr(notification, 'comment_id', None)
    if cid is not None:
        out['comment_id'] = str(int(cid))
    sender = getattr(notification, 'sender', None)
    if sender is not None and getattr(sender, 'username', None):
        out['sender_username'] = str(sender.username)
    return out


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


def _normalize_expo_push_tokens(tokens):
    out = []
    skipped = 0
    for t in tokens:
        s = (t or '').strip()
        if not s.startswith(_EXPO_TOKEN_PREFIX):
            skipped += 1
            continue
        out.append(s)
    if skipped:
        logger.warning('Expo push: %s jeton(s) ignoré(s) (format invalide, préfixe ExponentPushToken[ requis)', skipped)
    return out


def _expo_push_request_headers():
    expo_access = os.environ.get('EXPO_ACCESS_TOKEN', '').strip()
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate',
        'Content-Type': 'application/json',
    }
    if expo_access:
        headers['Authorization'] = f'Bearer {expo_access}'
    return headers


def _build_expo_message(token: str, payload_dict: dict) -> dict:
    return {
        'to': token,
        'title': str(payload_dict.get('title') or 'FOTOCE'),
        'body': str(payload_dict.get('body') or ''),
        'sound': 'default',
        'priority': 'high',
        'data': _expo_serializable_data(payload_dict),
    }


def _expo_post_messages(messages: list[dict], headers: dict) -> requests.Response:
    def _do() -> requests.Response:
        resp = requests.post(EXPO_PUSH_API_URL, json=messages, headers=headers, timeout=25)
        if resp.status_code >= 500 or resp.status_code == 429:
            raise ExternalRetryableError(f'Expo push HTTP {resp.status_code}')
        return resp

    batch_size = len(messages)
    return external_call(
        service='expo_push',
        operation=f'push/send batch={batch_size}',
        fn=_do,
        max_attempts=4,
    )


def _process_expo_response(body, resp, tokens_in_batch: list[str]) -> None:
    raw_text = resp.text
    text_snip = raw_text[:_EXPO_LOG_BODY_MAX] + ('…' if len(raw_text) > _EXPO_LOG_BODY_MAX else '')

    if isinstance(body, dict) and body.get('errors'):
        logger.warning(
            'Expo push erreurs globales batch=%s: %s | HTTP %s',
            len(tokens_in_batch),
            body['errors'],
            resp.status_code,
        )
        return

    if not resp.ok:
        logger.warning(
            'Expo push HTTP non OK batch=%s | status=%s | JSON: %s',
            len(tokens_in_batch),
            resp.status_code,
            body,
        )
        return

    tickets = _expo_tickets_from_batch_response(body)
    if not tickets:
        logger.warning(
            'Expo push réponse sans tickets batch=%s | HTTP %s | texte: %s',
            len(tokens_in_batch),
            resp.status_code,
            text_snip,
        )
        return

    for idx, ticket in enumerate(tickets):
        token = tokens_in_batch[idx] if idx < len(tokens_in_batch) else None
        token_hint = token[-16:] if token and len(token) > 16 else token
        if ticket.get('status') == 'ok':
            logger.debug(
                'Expo push OK batch | jeton …%s | id=%s',
                token_hint,
                ticket.get('id'),
            )
        else:
            logger.warning(
                'Expo push ticket erreur batch | jeton …%s | ticket: %s',
                token_hint,
                ticket,
            )
        if token and _expo_should_deactivate_token(ticket):
            ExpoPushToken.objects.filter(token=token).update(is_active=False)


def _send_expo_batch(tokens: list[str], payload_dict: dict, headers: dict) -> None:
    messages = [_build_expo_message(tok, payload_dict) for tok in tokens]
    try:
        resp = _expo_post_messages(messages, headers)
    except requests.RequestException as exc:
        logger.warning('Expo push batch échoué (%s jetons): %s', len(tokens), exc)
        return

    try:
        body = resp.json()
    except ValueError:
        logger.warning('Expo push batch — corps non JSON | HTTP %s', resp.status_code)
        return

    _process_expo_response(body, resp, tokens)


def _send_expo_mobile_for_user(recipient_user, payload_dict):
    token_list = _normalize_expo_push_tokens(
        ExpoPushToken.objects.filter(user=recipient_user, is_active=True).values_list('token', flat=True),
    )
    if not token_list:
        return
    headers = _expo_push_request_headers()
    for i in range(0, len(token_list), EXPO_PUSH_BATCH_SIZE):
        chunk = token_list[i : i + EXPO_PUSH_BATCH_SIZE]
        _send_expo_batch(chunk, payload_dict, headers)


def send_notification_push(notification, payload_dict=None):
    """
    Envoi Web Push (PWA — VAPID) + Expo Push (applications mobiles).
    Chaque canal est traité indépendamment selon les abonnements actifs du destinataire.
    """
    payload_dict = payload_dict or _notification_payload_dict(notification)
    recipient_user = notification.recipient
    _send_web_push_for_user(recipient_user, payload_dict)
    _send_expo_mobile_for_user(recipient_user, payload_dict)
