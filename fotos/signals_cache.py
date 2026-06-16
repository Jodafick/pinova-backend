"""Invalidation cache feed / stats à la création ou publication de foto."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .feed_cache import invalidate_home_feed_for_author_followers, invalidate_on_public_foto_change
from .models import Foto


def _foto_visible_in_feed(foto: Foto) -> bool:
    if foto.visibility == Foto.VISIBILITY_PRIVATE or foto.moderation_hidden:
        return False
    if foto.is_story and foto.story_ephemeral:
        return False
    now = timezone.now()
    if foto.scheduled_publish_at and foto.scheduled_publish_at > now:
        return False
    return True


@receiver(post_save, sender=Foto)
def invalidate_feed_cache_on_foto_save(sender, instance: Foto, created: bool, **kwargs):
    if not _foto_visible_in_feed(instance):
        return
    invalidate_on_public_foto_change(author_id=instance.author_id)
    if created:
        invalidate_home_feed_for_author_followers(instance.author)
