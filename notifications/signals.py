from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .push import send_notification_push
from .realtime import send_notification_ws

DELIVERY_WS_FALLBACK_PUSH = 'ws_fallback_push'
DELIVERY_WS_AND_PUSH = 'ws_and_push'
CRITICAL_PUSH_TYPES = {'payment', 'plan_change', 'board_invite'}


def _delivery_mode(notification) -> str:
    metadata = notification.metadata if isinstance(notification.metadata, dict) else {}
    mode = str(metadata.get('delivery_mode') or '').strip().lower()
    if mode in {DELIVERY_WS_FALLBACK_PUSH, DELIVERY_WS_AND_PUSH}:
        return mode
    if (notification.notification_type or '').strip().lower() in CRITICAL_PUSH_TYPES:
        return DELIVERY_WS_AND_PUSH
    return DELIVERY_WS_FALLBACK_PUSH


@receiver(post_save, sender=Notification)
def push_notification_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    mode = _delivery_mode(instance)
    ws_sent = send_notification_ws(instance)
    if mode == DELIVERY_WS_AND_PUSH:
        send_notification_push(instance)
        return
    if ws_sent:
        return
    send_notification_push(instance)


@receiver(post_save, sender=Notification)
def invalidate_unread_header_cache_on_notification_save(sender, instance, **kwargs):
    from pinova_backend.unread_notifications_middleware import (
        invalidate_unread_notifications_header_cache,
    )

    try:
        rid = int(instance.recipient_id)
    except (TypeError, ValueError):
        return
    invalidate_unread_notifications_header_cache(rid)
