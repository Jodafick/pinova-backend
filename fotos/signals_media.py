"""Purge fichier sur suppression d'instances (cascade Django, admin, etc.)."""

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Comment, Foto, FotoVariant
from .storage_media import unlink_field_file


@receiver(pre_delete, sender=FotoVariant)
def _purge_variant_image(sender, instance, **kwargs):
    unlink_field_file(instance.image)


@receiver(pre_delete, sender=Comment)
def _purge_comment_media(sender, instance, **kwargs):
    unlink_field_file(instance.media)


@receiver(pre_delete, sender=Foto)
def _purge_foto_main_media(sender, instance, **kwargs):
    # Variants déjà pré-supprimées (récepteurs pré_delete enfants puis cascade) :
    # ici uniquement médias du foto principal.
    unlink_field_file(instance.image)
    unlink_field_file(instance.story_video)
