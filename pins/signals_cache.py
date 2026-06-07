"""Invalidation cache feed / stats à la création ou publication de pin."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .feed_cache import invalidate_home_feed_for_author_followers, invalidate_on_public_pin_change
from .models import Pin


def _pin_visible_in_feed(pin: Pin) -> bool:
    if pin.visibility == Pin.VISIBILITY_PRIVATE or pin.moderation_hidden:
        return False
    if pin.is_story and pin.story_ephemeral:
        return False
    now = timezone.now()
    if pin.scheduled_publish_at and pin.scheduled_publish_at > now:
        return False
    return True


@receiver(post_save, sender=Pin)
def invalidate_feed_cache_on_pin_save(sender, instance: Pin, created: bool, **kwargs):
    if not _pin_visible_in_feed(instance):
        return
    invalidate_on_public_pin_change(author_id=instance.author_id)
    if created:
        invalidate_home_feed_for_author_followers(instance.author)
