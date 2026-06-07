"""
Politique de livraison notifications : WS, toast in-app (client), push Web/Expo.

Modes (`metadata.delivery_mode`, posé à la création si absent) :
  - ws_only          : centre de notifs + badge ; pas de push (ex. rang concours discret)
  - ws_fallback_push : push seulement si WS indisponible (social, défaut)
  - ws_and_push      : push systématique + WS (paiement, invite tableau, campagnes)

Regroupement push : types sociaux (`like`, `save`, `comment`, `follow`) partagent une
fenêtre par destinataire + clé de groupe ; une seule push par fenêtre, corps résumé si >1.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.core.cache import cache

from .push import _notification_payload_dict, send_notification_push
from .realtime import send_notification_ws

logger = logging.getLogger(__name__)

DELIVERY_WS_ONLY = 'ws_only'
DELIVERY_WS_FALLBACK_PUSH = 'ws_fallback_push'
DELIVERY_WS_AND_PUSH = 'ws_and_push'

CRITICAL_PUSH_TYPES = frozenset({'payment', 'plan_change', 'board_invite'})
CRITICAL_METADATA_KINDS = frozenset({
    'campaign_started',
    'campaign_boost_started',
    'contest_new_month',
    'referral_contest_new_month',
    'story_new_from_following',
})

SILENT_IN_APP_KINDS = frozenset({'contest_display_rank_change'})
SILENT_IN_APP_TYPES = frozenset({'digest'})

COALESCABLE_PUSH_TYPES = frozenset({'like', 'save', 'comment', 'follow'})
PUSH_COALESCE_TTL_SEC = 120

_COALESCE_CACHE_PREFIX = 'pinova:notif_push_coalesce:'


def _metadata(notification) -> dict[str, Any]:
    md = getattr(notification, 'metadata', None)
    return md if isinstance(md, dict) else {}


def resolve_delivery_mode(notification) -> str:
    md = _metadata(notification)
    mode = str(md.get('delivery_mode') or '').strip().lower()
    if mode in {DELIVERY_WS_ONLY, DELIVERY_WS_FALLBACK_PUSH, DELIVERY_WS_AND_PUSH}:
        return mode
    kind = str(md.get('kind') or '').strip().lower()
    if kind in CRITICAL_METADATA_KINDS:
        return DELIVERY_WS_AND_PUSH
    ntype = str(getattr(notification, 'notification_type', '') or '').strip().lower()
    if ntype in CRITICAL_PUSH_TYPES:
        return DELIVERY_WS_AND_PUSH
    if ntype in SILENT_IN_APP_TYPES or kind in SILENT_IN_APP_KINDS:
        return DELIVERY_WS_ONLY
    return DELIVERY_WS_FALLBACK_PUSH


def resolve_in_app_toast(notification) -> bool:
    md = _metadata(notification)
    if md.get('in_app_toast') is False:
        return False
    if md.get('in_app_toast') is True:
        return True
    kind = str(md.get('kind') or '').strip().lower()
    if kind in SILENT_IN_APP_KINDS:
        return False
    ntype = str(getattr(notification, 'notification_type', '') or '').strip().lower()
    if ntype in SILENT_IN_APP_TYPES:
        return False
    return True


def push_group_key(notification) -> str:
    ntype = str(getattr(notification, 'notification_type', '') or '').strip().lower()
    pin_id = getattr(notification, 'pin_id', None)
    if pin_id and ntype in COALESCABLE_PUSH_TYPES:
        return f'{ntype}:pin:{int(pin_id)}'
    sender_id = getattr(notification, 'sender_id', None)
    if ntype == 'follow' and sender_id:
        return f'follow:user:{int(sender_id)}'
    return f'{ntype}:general'


def _coalesce_cache_key(recipient_id: int, group_key: str) -> str:
    return f'{_COALESCE_CACHE_PREFIX}{recipient_id}:{group_key}'


def _coalesce_summary_body(notification, count: int) -> str:
    ntype = str(getattr(notification, 'notification_type', '') or '').strip().lower()
    title = (getattr(notification, 'title', None) or '').strip()
    if count <= 1:
        return (getattr(notification, 'message', None) or '').strip() or title or 'PINOVA'
    if ntype == 'like':
        return f"{count} nouvelles mentions J'aime"
    if ntype == 'save':
        return f'{count} nouveaux enregistrements sur vos pins'
    if ntype == 'comment':
        return f'{count} nouveaux commentaires'
    if ntype == 'follow':
        return f'{count} nouveaux abonnements'
    return f'{count} nouvelles notifications'


def _should_attempt_push(*, mode: str, ws_sent: bool) -> bool:
    if mode == DELIVERY_WS_ONLY:
        return False
    if mode == DELIVERY_WS_AND_PUSH:
        return True
    return not ws_sent


def _send_coalesced_push(notification, *, count: int) -> bool:
    payload = _notification_payload_dict(notification)
    if count > 1:
        payload['body'] = _coalesce_summary_body(notification, count)
        payload['title'] = (getattr(notification, 'title', None) or 'PINOVA').strip() or 'PINOVA'
        md = _metadata(notification)
        md = {**md, 'coalesced_count': count}
        payload['metadata_json'] = json.dumps(md, ensure_ascii=False, separators=(',', ':'))
    try:
        send_notification_push(notification, payload_dict=payload)
        return True
    except Exception:
        logger.exception('push delivery failed notification_id=%s', getattr(notification, 'id', None))
        return False


def _deliver_push(notification, *, mode: str, ws_sent: bool) -> bool:
    if not _should_attempt_push(mode=mode, ws_sent=ws_sent):
        return False

    ntype = str(getattr(notification, 'notification_type', '') or '').strip().lower()
    recipient_id = int(notification.recipient_id)
    if ntype not in COALESCABLE_PUSH_TYPES or mode == DELIVERY_WS_AND_PUSH:
        return _send_coalesced_push(notification, count=1)

    group = push_group_key(notification)
    cache_key = _coalesce_cache_key(recipient_id, group)
    state = cache.get(cache_key)
    if not isinstance(state, dict):
        state = {'count': 0, 'last_id': 0}

    state['count'] = int(state.get('count') or 0) + 1
    state['last_id'] = int(getattr(notification, 'id', 0) or 0)
    cache.set(cache_key, state, PUSH_COALESCE_TTL_SEC)

    if state['count'] > 1:
        return False

    return _send_coalesced_push(notification, count=1)


def deliver_notification(notification) -> dict[str, Any]:
    """
    Point d'entrée unique post-création : WS + push selon politique.
    Retourne un dict de télémétrie (logs structurés).
    """
    mode = resolve_delivery_mode(notification)
    ws_sent = send_notification_ws(notification)
    push_sent = _deliver_push(notification, mode=mode, ws_sent=ws_sent)

    payload = {
        'event': 'notification_delivery',
        'notification_id': notification.id,
        'recipient_id': notification.recipient_id,
        'delivery_mode': mode,
        'in_app_toast': resolve_in_app_toast(notification),
        'ws_sent': ws_sent,
        'push_sent': push_sent,
    }
    if not ws_sent and mode == DELIVERY_WS_FALLBACK_PUSH and push_sent:
        payload['degraded'] = 'push_only'
    logger.info(json.dumps(payload, ensure_ascii=False))
    return payload
