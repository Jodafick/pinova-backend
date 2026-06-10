"""Génération automatique des variantes média après sauvegarde d'un pin."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .media_variants import ensure_pin_feed_thumbnail
from .models import Pin


@receiver(post_save, sender=Pin)
def generate_pin_feed_thumbnail(sender, instance: Pin, created: bool, **kwargs):
    if not instance.image or not getattr(instance.image, 'name', ''):
        return
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'image' not in update_fields and not created:
        return
    try:
        ensure_pin_feed_thumbnail(instance, force=not created)
    except Exception:
        pass
