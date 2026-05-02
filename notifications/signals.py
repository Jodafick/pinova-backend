from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .push import send_notification_push


@receiver(post_save, sender=Notification)
def push_notification_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    send_notification_push(instance)
