"""Tests cache feed / stats (page 1, invalidation, X-Cache)."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Profile
from pins.feed_cache import get_home_feed_version
from pins.models import Pin


def _make_user(username: str) -> User:
    return User.objects.create_user(username=username, password='test-pass-123')


def _make_public_pin(author: User, title: str) -> Pin:
    return Pin.objects.create(
        author=author,
        title=title,
        slug=title.lower().replace(' ', '-'),
        visibility=Pin.VISIBILITY_PUBLIC,
    )


@override_settings(PINova_THROTTLE_DISABLE=True)
class FeedCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = _make_user('viewer')
        cls.viewer.profile.subscription_plan = Profile.PLAN_PRO
        cls.viewer.profile.partner_ads_enabled = False
        cls.viewer.profile.save(update_fields=['subscription_plan', 'partner_ads_enabled'])

        cls.author = _make_user('author')
        cls.author.profile.private_profile = False
        cls.author.profile.save(update_fields=['private_profile'])
        cls.viewer.profile.following.add(cls.author.profile)

        for i in range(12):
            _make_public_pin(cls.author, f'Cache Pin {i}')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def test_home_feed_page1_cache_hit(self):
        r1 = self.client.get('/api/pins/home-feed/?page=1&page_size=10')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1['X-Cache'], 'MISS')

        r2 = self.client.get('/api/pins/home-feed/?page=1&page_size=10')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2['X-Cache'], 'HIT')
        self.assertEqual(len(r2.data['results']), 10)

    def test_home_feed_invalidated_on_new_pin_from_following(self):
        self.client.get('/api/pins/home-feed/?page=1&page_size=10')
        ver_before = get_home_feed_version(self.viewer.id)

        _make_public_pin(self.author, 'Fresh Pin Burst')

        ver_after = get_home_feed_version(self.viewer.id)
        self.assertGreater(ver_after, ver_before)

        r3 = self.client.get('/api/pins/home-feed/?page=1&page_size=10')
        self.assertEqual(r3['X-Cache'], 'MISS')

    def test_discover_page1_global_cache(self):
        client = APIClient()
        r1 = client.get('/api/pins/discover/?page=1&page_size=10')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1['X-Cache'], 'MISS')

        r2 = client.get('/api/pins/discover/?page=1&page_size=10')
        self.assertEqual(r2['X-Cache'], 'HIT')

    def test_creator_stats_versioned_cache(self):
        self.viewer.profile.subscription_plan = Profile.PLAN_PRO
        self.viewer.profile.save(update_fields=['subscription_plan'])

        r1 = self.client.get('/api/pins/creator-stats/?totals_only=1')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1['X-Cache'], 'MISS')

        r2 = self.client.get('/api/pins/creator-stats/?totals_only=1')
        self.assertEqual(r2['X-Cache'], 'HIT')

        from pins.feed_cache import get_creator_stats_version

        ver_before = get_creator_stats_version(self.viewer.id)
        _make_public_pin(self.viewer, 'Viewer Own Pin')
        ver_after = get_creator_stats_version(self.viewer.id)
        self.assertGreater(ver_after, ver_before)

        r3 = self.client.get('/api/pins/creator-stats/?totals_only=1')
        self.assertEqual(r3['X-Cache'], 'MISS')

    def test_no_cache_bypass(self):
        self.client.get('/api/pins/home-feed/?page=1&page_size=10')
        r = self.client.get('/api/pins/home-feed/?page=1&page_size=10&no_cache=1')
        self.assertEqual(r['X-Cache'], 'MISS')

    def test_public_endpoints_allow_invalid_bearer(self):
        """Invité avec JWT périmé en localStorage : endpoints publics restent accessibles."""
        headers = {'HTTP_AUTHORIZATION': 'Bearer invalid.jwt.token'}
        for path in (
            '/api/pins/discover/?page=1&page_size=5',
            '/api/pins/topics/?limit=5',
            '/api/pins/explore-boards/?page=1&page_size=5',
        ):
            r = self.client.get(path, **headers)
            self.assertEqual(r.status_code, 200, msg=path)
