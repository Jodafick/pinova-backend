"""Tests cache partagé — throttling DRF et django-ratelimit entre « workers » simulés."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIRequestFactory

from fotoce_backend.config.cache import build_caches_config, warn_if_locmem_in_production
from fotoce_backend.security.throttling import AnonIPRateThrottle

SHARED_LOC = 'fotoce-shared-throttle-test'


class TwoPerMinuteAnonIPThrottle(AnonIPRateThrottle):
    """Sous-classe test : évite THROTTLE_RATES figé à l'import du module DRF."""

    rate = '2/minute'


THROTTLE_SETTINGS = {
    'CACHES': {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': SHARED_LOC,
            'TIMEOUT': 120,
        }
    },
    'RATELIMIT_USE_CACHE': 'default',
    'RATELIMIT_ENABLE': True,
}


@override_settings(**THROTTLE_SETTINGS)
class SharedDRFThrottleTests(TestCase):
    """Deux instances throttle = deux workers Gunicorn sur le même cache Redis/LocMem."""

    def setUp(self):
        cache.clear()

    def test_two_worker_instances_share_ip_burst_counter(self):
        factory = APIRequestFactory()
        request = factory.post('/api/auth/login/')
        request.META['REMOTE_ADDR'] = '203.0.113.50'
        request.user = AnonymousUser()

        worker_a = TwoPerMinuteAnonIPThrottle()
        worker_b = TwoPerMinuteAnonIPThrottle()

        self.assertTrue(worker_a.allow_request(request, None))
        self.assertTrue(worker_b.allow_request(request, None))
        self.assertFalse(worker_a.allow_request(request, None))


@override_settings(**THROTTLE_SETTINGS)
class SharedDjangoRatelimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_is_ratelimited_shared_between_two_calls(self):
        from django_ratelimit.core import is_ratelimited

        factory = APIRequestFactory()
        request = factory.post('/api/auth/login/')
        request.META['REMOTE_ADDR'] = '203.0.113.51'

        self.assertFalse(
            is_ratelimited(request, group='auth_login', key='ip', rate='2/m', method='POST', increment=True)
        )
        self.assertFalse(
            is_ratelimited(request, group='auth_login', key='ip', rate='2/m', method='POST', increment=True)
        )
        self.assertTrue(
            is_ratelimited(request, group='auth_login', key='ip', rate='2/m', method='POST', increment=True)
        )


class CacheConfigTests(SimpleTestCase):
    def test_build_caches_config_uses_redis_when_url_set(self):
        cfg = build_caches_config(redis_url='redis://127.0.0.1:6379/1', debug=False)
        self.assertEqual(cfg['default']['BACKEND'], 'django_redis.cache.RedisCache')
        self.assertEqual(cfg['default']['LOCATION'], 'redis://127.0.0.1:6379/1')

    def test_build_caches_config_falls_back_to_locmem(self):
        cfg = build_caches_config(redis_url='', debug=False)
        self.assertIn('LocMemCache', cfg['default']['BACKEND'])

    def test_warn_if_locmem_in_production_logs_warning(self):
        with self.assertLogs('fotoce.cache', level='WARNING') as captured:
            warn_if_locmem_in_production(redis_url='', debug=False)
        self.assertIn('REDIS_URL absent', captured.output[0])

    def test_no_warning_when_redis_or_debug(self):
        with self.assertNoLogs('fotoce.cache', level='WARNING'):
            warn_if_locmem_in_production(redis_url='redis://localhost/0', debug=False)
        with self.assertNoLogs('fotoce.cache', level='WARNING'):
            warn_if_locmem_in_production(redis_url='', debug=True)


class RatelimitExceptionHandlerTests(SimpleTestCase):
    def test_fotoce_exception_handler_maps_ratelimited_to_429(self):
        from fotoce_backend.core.exceptions import fotoce_exception_handler

        try:
            from django_ratelimit.exceptions import Ratelimited
        except ImportError:
            self.skipTest('django-ratelimit not installed')

        response = fotoce_exception_handler(Ratelimited(), {})
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data['code'], 'fotoce_rate_limited')
