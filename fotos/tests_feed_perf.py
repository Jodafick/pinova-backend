"""Tests perf feed — budget requêtes DB (assertNumQueries)."""

import statistics
import time

from django.contrib.auth.models import User
from django.core.cache.backends.locmem import LocMemCache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Profile
from fotos.feed_queryset import feed_serializer_context, optimize_foto_feed_queryset
from fotos.models import Like, Foto, Save
from fotos.pagination import FotoFeedPagination
from fotos.serializers import FotoSerializer
from fotos.views import FotoViewSet

LOC_MEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'pins-feed-perf-tests',
    }
}

FEED_PERF_SETTINGS = {
    'CACHES': LOC_MEM_CACHES,
    'PINova_THROTTLE_DISABLE': True,
    'DEBUG': True,
    'SECURE_SSL_REDIRECT': False,
}


def _make_user(username: str) -> User:
    return User.objects.create_user(username=username, password='test-pass-123')


def _make_public_pin(author: User, title: str) -> Foto:
    return Foto.objects.create(
        author=author,
        title=title,
        slug=title.lower().replace(' ', '-'),
        visibility=Foto.VISIBILITY_PUBLIC,
    )


@override_settings(**FEED_PERF_SETTINGS)
class FeedQueryBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = _make_user('viewer')
        cls.viewer.profile.subscription_plan = Profile.PLAN_PRO
        cls.viewer.profile.partner_ads_enabled = False
        cls.viewer.profile.save(update_fields=['subscription_plan', 'partner_ads_enabled'])

        cls.authors = []
        cls.fotos = []
        for i in range(12):
            author = _make_user(f'creator{i}')
            author.profile.private_profile = False
            author.profile.save(update_fields=['private_profile'])
            cls.viewer.profile.following.add(author.profile)
            cls.authors.append(author)
            foto = _make_public_pin(author, f'Foto Feed {i}')
            cls.fotos.append(foto)
            if i < 3:
                Like.objects.create(user=cls.viewer, foto=pin)
            if i < 2:
                Save.objects.create(user=cls.viewer, foto=pin)

        cls.stranger = _make_user('stranger')
        cls.stranger.profile.private_profile = False
        cls.stranger.profile.save(update_fields=['private_profile'])
        for i in range(6):
            _make_public_pin(cls.stranger, f'Discover Foto {i}')

    # Budget SQL home_feed (HTTP, ads off, no_cache) — mesuré 2026-06-06 :
    # 1 following M2M, 2-3 blocks, 2 counts, ≤2 slices SELECT, 3 prefetch = ≤12
    HOME_FEED_QUERY_BUDGET = 13

    def setUp(self):
        LocMemCache('pins-feed-perf-tests', {}).clear()
        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def test_following_feed_page_five_queries(self):
        """Budget foto feed : COUNT + SELECT + 3 prefetch (hors following / blocking / ads)."""
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory, force_authenticate

        factory = APIRequestFactory()
        req = factory.get('/api/fotos/following/?page=1&page_size=10')
        force_authenticate(req, user=self.viewer)
        drf_request = Request(req)

        rows = list(self.viewer.profile.following.values_list('pk', 'user_id'))
        drf_request._viewer_following_profile_ids = frozenset(r[0] for r in rows)
        following_user_ids = [r[1] for r in rows]

        viewset = FotoViewSet()
        viewset.action = 'following'
        viewset.request = drf_request
        qs = (
            viewset.get_queryset()
            .filter(author_id__in=following_user_ids)
            .exclude(author=self.viewer)
        )
        qs = optimize_foto_feed_queryset(qs, drf_request)

        paginator = FotoFeedPagination()
        with self.assertNumQueries(5):
            page = paginator.paginate_queryset(qs, drf_request)
            list(page)

    def test_following_feed_http_returns_ten_pins(self):
        response = self.client.get('/api/fotos/following/?page=1&page_size=10&no_cache=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 10)

    def test_home_feed_http_query_budget(self):
        """Endpoint HTTP home-feed : ≤ 15 requêtes SQL (following + discover + optimize + ads off)."""
        with self.assertNumQueries(self.HOME_FEED_QUERY_BUDGET):
            response = self.client.get(
                '/api/fotos/home-feed/?page=1&page_size=10&no_cache=1',
            )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data.get('results', [])), 1)

    def test_home_feed_p95_latency_under_500ms(self):
        """p95 latence locale home_feed (10 échantillons, cache bypass)."""
        durations_ms: list[float] = []
        for _ in range(12):
            t0 = time.perf_counter()
            response = self.client.get('/api/fotos/home-feed/?page=1&page_size=10&no_cache=1')
            self.assertEqual(response.status_code, 200)
            durations_ms.append((time.perf_counter() - t0) * 1000.0)
        p95 = statistics.quantiles(durations_ms, n=20)[18]
        self.assertLess(
            p95,
            500.0,
            f'p95 home_feed={p95:.1f}ms (samples={durations_ms})',
        )

    def test_feed_serialization_zero_extra_queries(self):
        """Après optimize_foto_feed_queryset, FotoSerializer ne déclenche plus de N+1."""
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory, force_authenticate

        factory = APIRequestFactory()
        request = factory.get('/api/fotos/following/?page=1&page_size=10')
        force_authenticate(request, user=self.viewer)
        drf_request = Request(request)

        rows = list(self.viewer.profile.following.values_list('pk', 'user_id'))
        drf_request._viewer_following_profile_ids = frozenset(r[0] for r in rows)
        following_user_ids = [r[1] for r in rows]

        queryset = (
            Foto.objects.filter(author_id__in=following_user_ids)
            .exclude(author=self.viewer)
            .select_related('author', 'author__profile', 'topic')
        )
        queryset = optimize_foto_feed_queryset(queryset, drf_request)[:10]
        fotos = list(queryset)

        ctx = feed_serializer_context(drf_request, {'request': drf_request})
        with self.assertNumQueries(0):
            data = FotoSerializer(pins, many=True, context=ctx).data

        self.assertEqual(len(data), 10)
        self.assertIn('is_boosted', data[0])

    def test_annotated_flags_reflect_viewer_state(self):
        from rest_framework.test import APIRequestFactory, force_authenticate

        factory = APIRequestFactory()
        request = factory.get('/api/fotos/following/')
        force_authenticate(request, user=self.viewer)
        from rest_framework.request import Request
        drf_request = Request(request)
        drf_request.user = self.viewer

        foto = self.pins[0]
        qs = optimize_foto_feed_queryset(Foto.objects.filter(pk=pin.pk), drf_request)
        item = qs.get()
        self.assertTrue(item._is_liked)
        self.assertTrue(item._is_saved)

        pin2 = self.pins[5]
        qs2 = optimize_foto_feed_queryset(Foto.objects.filter(pk=pin2.pk), drf_request)
        item2 = qs2.get()
        self.assertFalse(item2._is_liked)
