"""Génération automatique des variantes média après sauvegarde d'un foto."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .media_variants import ensure_foto_feed_thumbnail
from .models import Foto


@receiver(post_save, sender=Foto)
def generate_foto_feed_thumbnail(sender, instance: Foto, created: bool, **kwargs):
    if not instance.image or not getattr(instance.image, 'name', ''):
        return
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'image' not in update_fields and not created:
        return
    try:
        ensure_foto_feed_thumbnail(instance, force=not created)
    except Exception:
        pass
