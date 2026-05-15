import json
import logging
import os
from urllib.parse import quote

import requests
from pywebpush import WebPushException, webpush

from .models import ExpoPushToken, PushSubscription

logger = logging.getLogger(__name__)

EXPO_PUSH_API_URL = 'https://exp.host/--/api/v2/push/send'

_EXPO_TOKEN_PREFIX = 'ExponentPushToken['

# Limite prudente pour les logs (évite des fichiers énormes si Expo renvoie une erreur verbose).
_EXPO_LOG_BODY_MAX = 16000


def _expo_ticket_from_send_response(body):
    """
    Pour une requête « un seul message », Expo renvoie `data` comme objet ticket,
    pas toujours comme tableau — ne jamais présumer len(data) == nombre de jetons.
    """
    if not isinstance(body, dict):
        return None
    data = body.get('data')
    if isinstance(data, dict) and data.get('status') is not None:
        return data
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    return None


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
    slug = getattr(notification, 'pin_slug', None)
    metadata = getattr(notification, 'metadata', None)
    if not isinstance(metadata, dict):
        metadata = {}
    out = {
        'title': notification.title or 'PINOVA',
        'body': notification.message,
        'notification_type': notification.notification_type,
        'action_url': _push_action_url(notification),
        'notification_id': notification.id,
        'metadata_json': json.dumps(metadata, ensure_ascii=False, separators=(',', ':')),
    }
    if slug:
        out['pin_slug'] = str(slug)
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
    """Ne garde que les jetons au format Expo attendu (évite des POST inutiles / erreurs silencieuses)."""
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
    }
    if expo_access:
        headers['Authorization'] = f'Bearer {expo_access}'
    return headers


def _send_single_expo_notification(token, payload_dict, headers):
    """
    Une requête HTTP = une notification (payload objet unique, pas tableau).
    Utilise json= pour que requests impose Content-Type application/json et sérialise comme Expo le attend.
    """
    data_payload = _expo_serializable_data(payload_dict)
    # Pas de channelId arbitraire : si absent, Expo gère le canal Default (voir doc Expo Push).
    message = {
        'to': token,
        'title': str(payload_dict.get('title') or 'PINOVA'),
        'body': str(payload_dict.get('body') or ''),
        'sound': 'default',
        'priority': 'high',
        'data': data_payload,
    }
    token_hint = token[-16:] if len(token) > 16 else token

    try:
        resp = requests.post(
            EXPO_PUSH_API_URL,
            json=message,
            headers=headers,
            timeout=25,
        )
    except requests.RequestException as exc:
        logger.warning('Expo push requête échouée (jeton …%s): %s', token_hint, exc)
        return

    raw_text = resp.text
    text_snip = raw_text[:_EXPO_LOG_BODY_MAX] + ('…' if len(raw_text) > _EXPO_LOG_BODY_MAX else '')

    try:
        body = resp.json()
    except ValueError:
        logger.warning(
            'Expo push HTTP %s — corps non JSON (jeton …%s) — texte brut: %s',
            resp.status_code,
            token_hint,
            text_snip,
        )
        return

    # Détail complet réservé au niveau DEBUG (évite de saturer les logs en prod).
    logger.debug(
        'Expo push réponse brute HTTP %s | jeton …%s | JSON: %s | texte: %s',
        resp.status_code,
        token_hint,
        body,
        text_snip,
    )

    if isinstance(body, dict) and body.get('errors'):
        logger.warning(
            'Expo push erreurs globales (jeton …%s): %s | HTTP %s | JSON complet: %s | texte brut: %s',
            token_hint,
            body['errors'],
            resp.status_code,
            body,
            text_snip,
        )
        return

    if not resp.ok:
        logger.warning(
            'Expo push HTTP non OK (jeton …%s) | status=%s | JSON complet: %s | texte brut: %s',
            token_hint,
            resp.status_code,
            body,
            text_snip,
        )
        return

    ticket = _expo_ticket_from_send_response(body)
    if ticket is None:
        logger.warning(
            'Expo push réponse sans ticket exploitable (jeton …%s) | HTTP %s | JSON complet: %s | texte brut: %s',
            token_hint,
            resp.status_code,
            body,
            text_snip,
        )
        return

    ticket_status = ticket.get('status')
    ticket_id = ticket.get('id')
    if ticket_status == 'ok':
        logger.info(
            'Expo push OK | HTTP %s | jeton …%s | ticket status=%s | id=%s',
            resp.status_code,
            token_hint,
            ticket_status,
            ticket_id,
        )
    else:
        logger.warning(
            'Expo push ticket erreur (jeton …%s) | HTTP %s | ticket: %s | JSON complet: %s | texte brut: %s',
            token_hint,
            resp.status_code,
            ticket,
            body,
            text_snip,
        )

    if _expo_should_deactivate_token(ticket):
        ExpoPushToken.objects.filter(token=token).update(is_active=False)


def _send_expo_mobile_for_user(recipient_user, payload_dict):
    token_list = _normalize_expo_push_tokens(
        ExpoPushToken.objects.filter(user=recipient_user, is_active=True).values_list('token', flat=True),
    )
    if not token_list:
        return
    headers = _expo_push_request_headers()
    for tok in token_list:
        _send_single_expo_notification(tok, payload_dict, headers)


def send_notification_push(notification):
    """
    Envoi Web Push (PWA — VAPID) + Expo Push (applications mobiles).
    Chaque canal est traité indépendamment selon les abonnements actifs du destinataire.
    """
    payload_dict = _notification_payload_dict(notification)
    recipient_user = notification.recipient
    _send_web_push_for_user(recipient_user, payload_dict)
    _send_expo_mobile_for_user(recipient_user, payload_dict)
