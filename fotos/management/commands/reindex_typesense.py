"""Réindexation complète Typesense (pins, users, boards)."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from fotos.models import Board, Foto
from fotos.search import documents, typesense_client
from fotos.search.schemas import BOARDS_COLLECTION, FOTOS_COLLECTION, USERS_COLLECTION


class Command(BaseCommand):
    help = 'Réindexe fotos, users et boards dans Typesense (SEARCH_ENGINE=typesense).'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=500)

    def handle(self, *args, **options):
        batch_size = max(50, int(options['batch_size']))
        typesense_client.ensure_collections()
        self.stdout.write('Collections Typesense prêtes.')

        pin_qs = Foto.objects.select_related('author__profile').prefetch_related('hashtags').order_by('pk')
        total_pins = 0
        batch: list[dict] = []
        for foto in pin_qs.iterator(chunk_size=batch_size):
            if documents.pin_searchable(foto):
                batch.append(documents.pin_to_typesense_doc(foto))
            if len(batch) >= batch_size:
                typesense_client.get_typesense_client().collections[FOTOS_COLLECTION].documents.import_(
                    batch, {'action': 'upsert'}
                )
                total_pins += len(batch)
                batch = []
        if batch:
            typesense_client.get_typesense_client().collections[FOTOS_COLLECTION].documents.import_(
                batch, {'action': 'upsert'}
            )
            total_pins += len(batch)
        self.stdout.write(self.style.SUCCESS(f'Pins indexés : {total_pins}'))

        user_batch: list[dict] = []
        total_users = 0
        for user in User.objects.select_related('profile').order_by('pk').iterator(chunk_size=batch_size):
            doc = documents.user_to_typesense_doc(user)
            if doc and doc.get('discoverable_profile'):
                user_batch.append(doc)
            if len(user_batch) >= batch_size:
                typesense_client.get_typesense_client().collections[USERS_COLLECTION].documents.import_(
                    user_batch, {'action': 'upsert'}
                )
                total_users += len(user_batch)
                user_batch = []
        if user_batch:
            typesense_client.get_typesense_client().collections[USERS_COLLECTION].documents.import_(
                user_batch, {'action': 'upsert'}
            )
            total_users += len(user_batch)
        self.stdout.write(self.style.SUCCESS(f'Users indexés : {total_users}'))

        board_batch: list[dict] = []
        total_boards = 0
        for board in Board.objects.select_related('user').prefetch_related('collaborators').order_by('pk').iterator(
            chunk_size=batch_size
        ):
            board_batch.append(documents.board_to_typesense_doc(board))
            if len(board_batch) >= batch_size:
                typesense_client.get_typesense_client().collections[BOARDS_COLLECTION].documents.import_(
                    board_batch, {'action': 'upsert'}
                )
                total_boards += len(board_batch)
                board_batch = []
        if board_batch:
            typesense_client.get_typesense_client().collections[BOARDS_COLLECTION].documents.import_(
                board_batch, {'action': 'upsert'}
            )
            total_boards += len(board_batch)
        self.stdout.write(self.style.SUCCESS(f'Boards indexés : {total_boards}'))
