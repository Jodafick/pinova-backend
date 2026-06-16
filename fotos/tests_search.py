"""Tests recherche — pg_trgm, fallback legacy, Typesense mock."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings

from accounts.models import Profile
from fotos.models import Board, Hashtag, Foto, Topic
from fotos.search.service import (
    discover_pins_filter,
    pin_matches_query,
    search_boards,
    search_pins,
    search_users,
)
from fotos.search_utils import broad_foto_q, fuzzy_score


class SearchUtilsTests(TestCase):
    def test_fuzzy_score_substring_boost(self):
        self.assertGreater(fuzzy_score('tattoo', 'Summer tattoo vibes'), 0.9)

    def test_broad_foto_q_matches_title_token(self):
        author = User.objects.create_user('alice', password='x')
        foto = Foto.objects.create(title='Minimal salon design', author=author, slug='minimal-salon')
        qs = Foto.objects.filter(broad_foto_q('salon'))
        self.assertIn(pin, qs)


@override_settings(SEARCH_USE_TRIGRAM=False, SEARCH_ENGINE='postgres')
class LegacySearchServiceTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('creator', password='x')
        Profile.objects.get_or_create(user=self.author, defaults={'display_name': 'Creator Studio'})
        self.pin = Foto.objects.create(
            title='Rose tattoo flash',
            description='Ink art',
            author=self.author,
            slug='rose-tattoo',
        )
        tag = Hashtag.objects.create(name='tattoo')
        self.pin.hashtags.add(tag)

    def test_search_fotos_legacy_path(self):
        qs = Foto.objects.filter(visibility=Foto.VISIBILITY_PUBLIC)
        results = search_pins(qs, 'tattoo', limit=5)
        self.assertTrue(any(p.pk == self.pin.pk for p in results))

    def test_search_users_legacy_path(self):
        qs = User.objects.filter(profile__discoverable_profile=True)
        results = search_users(qs, 'creator', limit=5)
        self.assertTrue(any(u.username == 'creator' for u in results))

    def test_search_boards_legacy_path(self):
        board = Board.objects.create(user=self.author, name='Tattoo references', description='Flash sheets')
        qs = Board.objects.filter(is_private=False)
        results = search_boards(qs, 'tattoo', limit=5)
        self.assertTrue(any(b.pk == board.pk for b in results))

    def test_discover_pins_filter_legacy(self):
        qs = Foto.objects.filter(visibility=Foto.VISIBILITY_PUBLIC)
        filtered = discover_pins_filter(qs, 'rose')
        self.assertIn(self.pin, filtered)

    def test_foto_matches_query_legacy(self):
        self.assertTrue(pin_matches_query(self.pin, 'rose'))


@override_settings(
    SEARCH_ENGINE='typesense',
    TYPESENSE_HOST='localhost:8108',
    TYPESENSE_API_KEY='test',
    CELERY_TASK_ALWAYS_EAGER=True,
)
class TypesenseFallbackTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('typesense_user', password='x')
        self.pin = Foto.objects.create(title='Typesense foto', author=self.author, slug='typesense-pin')

    @mock.patch('fotos.search.typesense_client.search_foto_ids', side_effect=RuntimeError('down'))
    @mock.patch('fotos.search.tasks.sync_user_typesense')
    def test_search_fotos_falls_back_when_typesense_down(self, _mock_sync, _mock_search):
        with override_settings(SEARCH_USE_TRIGRAM=False):
            results = search_pins(Foto.objects.all(), 'typesense', limit=5)
        self.assertTrue(any(p.pk == self.pin.pk for p in results))

    @mock.patch('fotos.signals_search.sync_foto_typesense.delay')
    def test_typesense_sync_lag_does_not_block_http_search(self, mock_delay):
        """Signal Celery en file — recherche HTTP reste servie (Postgres fallback si TS down)."""
        mock_delay.return_value = None

        foto = Foto.objects.create(title='Lag sync foto', author=self.author, slug='lag-sync-pin')
        mock_delay.assert_called()
        with mock.patch('fotos.search.typesense_client.search_foto_ids', side_effect=RuntimeError('down')):
            with override_settings(SEARCH_USE_TRIGRAM=False):
                results = search_pins(Foto.objects.filter(pk=pin.pk), 'lag', limit=5)
        self.assertTrue(any(p.pk == foto.pk for p in results))


class PostgresTrigramTests(TestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('pg_trgm tests require PostgreSQL')
        self.author = User.objects.create_user('pguser', password='x')
        Profile.objects.filter(user=self.author).update(display_name='PG Artist')
        self.pin = Foto.objects.create(
            title='PostgreSQL indexed title',
            author=self.author,
            slug='pg-index-title',
        )

    @override_settings(SEARCH_USE_TRIGRAM=True, SEARCH_ENGINE='postgres')
    def test_search_fotos_postgres_trgm(self):
        qs = Foto.objects.filter(visibility=Foto.VISIBILITY_PUBLIC)
        results = search_pins(qs, 'postgres', limit=5)
        self.assertTrue(any(p.pk == self.pin.pk for p in results))
