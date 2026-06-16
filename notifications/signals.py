from django.db.models.signals import post_save
from django.dispatch import receiver

from fotoce_backend.middleware.unread_notifications import (
    invalidate_unread_notifications_header_cache,
)

from .delivery import deliver_notification
from .models import Notification


@receiver(post_save, sender=Notification)
def push_notification_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    deliver_notification(instance)


@receiver(post_save, sender=Notification)
def invalidate_unread_header_cache_on_notification_save(sender, instance, **kwargs):
    try:
        rid = int(instance.recipient_id)
    except (TypeError, ValueError):
        return
    invalidate_unread_notifications_header_cache(rid)
