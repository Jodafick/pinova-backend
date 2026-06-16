"""Sync index search Typesense sur create/update/delete."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import Profile
from fotos.models import Board, Foto
from fotos.search.tasks import (
    delete_board_typesense,
    delete_foto_typesense,
    sync_board_typesense,
    sync_foto_typesense,
    sync_user_typesense,
)


def _typesense_sync_enabled() -> bool:
    if getattr(settings, 'SEARCH_ENGINE', 'postgres') != 'typesense':
        return False
    from fotos.search.typesense_client import typesense_configured

    return typesense_configured()


@receiver(post_save, sender=Foto)
def enqueue_foto_search_sync(sender, instance: Foto, **kwargs):
    if not _typesense_sync_enabled():
        return
    sync_foto_typesense.delay(instance.pk)


@receiver(post_delete, sender=Foto)
def enqueue_foto_search_delete(sender, instance: Foto, **kwargs):
    if not _typesense_sync_enabled():
        return
    delete_foto_typesense.delay(instance.pk)


@receiver(post_save, sender=Board)
def enqueue_board_search_sync(sender, instance: Board, **kwargs):
    if not _typesense_sync_enabled():
        return
    sync_board_typesense.delay(instance.pk)


@receiver(post_delete, sender=Board)
def enqueue_board_search_delete(sender, instance: Board, **kwargs):
    if not _typesense_sync_enabled():
        return
    delete_board_typesense.delay(instance.pk)


@receiver(post_save, sender=User)
def enqueue_user_search_sync(sender, instance: User, **kwargs):
    if not _typesense_sync_enabled():
        return
    sync_user_typesense.delay(instance.pk)


@receiver(post_save, sender=Profile)
def enqueue_profile_search_sync(sender, instance: Profile, **kwargs):
    if not _typesense_sync_enabled():
        return
    sync_user_typesense.delay(instance.user_id)
