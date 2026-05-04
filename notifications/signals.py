from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .push import send_notification_push


@receiver(post_save, sender=Notification)
def push_notification_on_create(sender, instance, created, **kwargs):
    if not created:
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
