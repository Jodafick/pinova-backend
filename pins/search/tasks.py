"""Tâches Celery — sync index Typesense (Phase 2)."""

from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth.models import User

from accounts.models import Profile
from pinova_backend.celery import PinovaTask
from pins.models import Board, Pin
from pins.search import documents, typesense_client
from pins.search.schemas import BOARDS_COLLECTION, PINS_COLLECTION, USERS_COLLECTION

logger = logging.getLogger('pinova.search.sync')


def _typesense_enabled() -> bool:
    from django.conf import settings
    from pins.search.typesense_client import typesense_configured

    return getattr(settings, 'SEARCH_ENGINE', 'postgres') == 'typesense' and typesense_configured()


@shared_task(bind=True, base=PinovaTask, name='pins.sync_pin_typesense')
def sync_pin_typesense(self, pin_id: int) -> dict:
    if not _typesense_enabled():
        return {'skipped': True, 'reason': 'SEARCH_ENGINE!=typesense'}
    try:
        pin = Pin.objects.select_related('author__profile').prefetch_related('hashtags').get(pk=pin_id)
    except Pin.DoesNotExist:
        try:
            typesense_client.delete_document(PINS_COLLECTION, str(pin_id))
        except typesense_client.TypesenseUnavailable:
            return {'skipped': True, 'reason': 'typesense_unavailable'}
        return {'deleted': pin_id}
    if not documents.pin_searchable(pin):
        try:
            typesense_client.delete_document(PINS_COLLECTION, str(pin_id))
        except typesense_client.TypesenseUnavailable:
            return {'skipped': True, 'reason': 'typesense_unavailable'}
        return {'deleted': pin_id, 'reason': 'not_searchable'}
    try:
        typesense_client.upsert_document(PINS_COLLECTION, documents.pin_to_typesense_doc(pin))
    except typesense_client.TypesenseUnavailable:
        return {'skipped': True, 'reason': 'typesense_unavailable'}
    return {'upserted': pin_id}


@shared_task(bind=True, base=PinovaTask, name='pins.delete_pin_typesense')
def delete_pin_typesense(self, pin_id: int) -> dict:
    if not _typesense_enabled():
        return {'skipped': True}
    typesense_client.delete_document(PINS_COLLECTION, str(pin_id))
    return {'deleted': pin_id}


@shared_task(bind=True, base=PinovaTask, name='pins.sync_user_typesense')
def sync_user_typesense(self, user_id: int) -> dict:
    if not _typesense_enabled():
        return {'skipped': True}
    try:
        user = User.objects.select_related('profile').get(pk=user_id)
    except User.DoesNotExist:
        try:
            typesense_client.delete_document(USERS_COLLECTION, str(user_id))
        except typesense_client.TypesenseUnavailable:
            return {'skipped': True, 'reason': 'typesense_unavailable'}
        return {'deleted': user_id}
    doc = documents.user_to_typesense_doc(user)
    if not doc or not doc.get('discoverable_profile'):
        try:
            typesense_client.delete_document(USERS_COLLECTION, str(user_id))
        except typesense_client.TypesenseUnavailable:
            return {'skipped': True, 'reason': 'typesense_unavailable'}
        return {'deleted': user_id}
    try:
        typesense_client.upsert_document(USERS_COLLECTION, doc)
    except typesense_client.TypesenseUnavailable:
        return {'skipped': True, 'reason': 'typesense_unavailable'}
    return {'upserted': user_id}


@shared_task(bind=True, base=PinovaTask, name='pins.sync_board_typesense')
def sync_board_typesense(self, board_id: int) -> dict:
    if not _typesense_enabled():
        return {'skipped': True}
    try:
        board = Board.objects.select_related('user').prefetch_related('collaborators').get(pk=board_id)
    except Board.DoesNotExist:
        try:
            typesense_client.delete_document(BOARDS_COLLECTION, str(board_id))
        except typesense_client.TypesenseUnavailable:
            return {'skipped': True, 'reason': 'typesense_unavailable'}
        return {'deleted': board_id}
    try:
        typesense_client.upsert_document(BOARDS_COLLECTION, documents.board_to_typesense_doc(board))
    except typesense_client.TypesenseUnavailable:
        return {'skipped': True, 'reason': 'typesense_unavailable'}
    return {'upserted': board_id}


@shared_task(bind=True, base=PinovaTask, name='pins.delete_board_typesense')
def delete_board_typesense(self, board_id: int) -> dict:
    if not _typesense_enabled():
        return {'skipped': True}
    typesense_client.delete_document(BOARDS_COLLECTION, str(board_id))
    return {'deleted': board_id}


@shared_task(bind=True, base=PinovaTask, name='pins.reindex_typesense')
def reindex_typesense(self, batch_size: int = 500) -> dict:
    if not _typesense_enabled():
        return {'skipped': True}
    from django.core.management import call_command

    call_command('reindex_typesense', batch_size=batch_size)
    return {'reindexed': True, 'batch_size': batch_size}
