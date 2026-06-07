import json
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .push import send_notification_push
from .realtime import send_notification_ws

logger = logging.getLogger(__name__)

DELIVERY_WS_FALLBACK_PUSH = 'ws_fallback_push'
DELIVERY_WS_AND_PUSH = 'ws_and_push'
CRITICAL_PUSH_TYPES = {'payment', 'plan_change', 'board_invite'}
CRITICAL_METADATA_KINDS = {
    'campaign_started',
    'campaign_boost_started',
    'contest_new_month',
    'referral_contest_new_month',
    'story_new_from_following',
}


def _delivery_mode(notification) -> str:
    metadata = notification.metadata if isinstance(notification.metadata, dict) else {}
    mode = str(metadata.get('delivery_mode') or '').strip().lower()
    if mode in {DELIVERY_WS_FALLBACK_PUSH, DELIVERY_WS_AND_PUSH}:
        return mode
    kind = str(metadata.get('kind') or '').strip().lower()
    if kind in CRITICAL_METADATA_KINDS:
        return DELIVERY_WS_AND_PUSH
    if (notification.notification_type or '').strip().lower() in CRITICAL_PUSH_TYPES:
        return DELIVERY_WS_AND_PUSH
    return DELIVERY_WS_FALLBACK_PUSH


def _log_delivery(notification, *, mode: str, ws_sent: bool, push: bool) -> None:
    payload = {
        'event': 'notification_delivery',
        'notification_id': notification.id,
        'recipient_id': notification.recipient_id,
        'delivery_mode': mode,
        'ws_sent': ws_sent,
        'push_sent': push,
    }
    if not ws_sent and mode == DELIVERY_WS_FALLBACK_PUSH:
        payload['degraded'] = 'push_only'
    logger.info(json.dumps(payload, ensure_ascii=False))


@receiver(post_save, sender=Notification)
def push_notification_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    mode = _delivery_mode(instance)
    ws_sent = send_notification_ws(instance)
    if mode == DELIVERY_WS_AND_PUSH:
        send_notification_push(instance)
        _log_delivery(instance, mode=mode, ws_sent=ws_sent, push=True)
        return
    if ws_sent:
        _log_delivery(instance, mode=mode, ws_sent=True, push=False)
        return
    send_notification_push(instance)
    _log_delivery(instance, mode=mode, ws_sent=False, push=True)


@receiver(post_save, sender=Notification)
def invalidate_unread_header_cache_on_notification_save(sender, instance, **kwargs):
    from pinova_backend.middleware.unread_notifications import (
        invalidate_unread_notifications_header_cache,
    )

    try:
        rid = int(instance.recipient_id)
    except (TypeError, ValueError):
        return
    invalidate_unread_notifications_header_cache(rid)
