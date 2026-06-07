"""Tests checks deploy — Redis channel layer production."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


@override_settings(DEBUG=False, CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class DeployChannelLayerCheckTests(SimpleTestCase):
    def test_inmemory_rejected_in_production(self):
        from pinova_backend.core.checks import check_redis_channel_layer_in_production

        errors = check_redis_channel_layer_in_production(None)
        ids = [e.id for e in errors]
        self.assertIn('pinova.E003', ids)

    @override_settings(
        DEBUG=False,
        CHANNEL_LAYERS={
            'default': {
                'BACKEND': 'channels_redis.core.RedisChannelLayer',
                'CONFIG': {'hosts': ['redis://localhost:6379/0']},
            },
        },
    )
    @patch('pinova_backend.core.checks.redis_url_from_env', return_value='redis://localhost:6379/0')
    def test_redis_backend_passes_when_redis_url_set(self, _mock_redis):
        from pinova_backend.core.checks import check_redis_channel_layer_in_production

        errors = check_redis_channel_layer_in_production(None)
        self.assertEqual(errors, [])

    @override_settings(
        DEBUG=False,
        CHANNEL_LAYERS={
            'default': {
                'BACKEND': 'channels_redis.core.RedisChannelLayer',
                'CONFIG': {'hosts': ['redis://localhost:6379/0']},
            },
        },
    )
    @patch('pinova_backend.core.checks.redis_url_from_env', return_value='')
    def test_missing_redis_url_fails_deploy_check(self, _mock_redis):
        from pinova_backend.core.checks import check_redis_channel_layer_in_production

        errors = check_redis_channel_layer_in_production(None)
        self.assertTrue(any(e.id == 'pinova.E004' for e in errors))


@override_settings(DEBUG=False, CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class DeployRedisCacheCheckTests(SimpleTestCase):
    @patch('pinova_backend.core.checks.redis_url_from_env', return_value='')
    def test_locmem_cache_rejected_in_production(self, _mock_redis):
        from pinova_backend.core.checks import check_redis_cache_in_production

        errors = check_redis_cache_in_production(None)
        ids = [e.id for e in errors]
        self.assertIn('pinova.E005', ids)

    @override_settings(
        DEBUG=False,
        CACHES={
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': 'redis://localhost:6379/0',
            },
        },
    )
    @patch('pinova_backend.core.checks.redis_url_from_env', return_value='')
    def test_missing_redis_url_fails_cache_deploy_check(self, _mock_redis):
        from pinova_backend.core.checks import check_redis_cache_in_production

        errors = check_redis_cache_in_production(None)
        self.assertTrue(any(e.id == 'pinova.E006' for e in errors))

    @override_settings(
        DEBUG=False,
        CACHES={
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': 'redis://localhost:6379/0',
            },
        },
    )
    @patch('pinova_backend.core.checks.redis_url_from_env', return_value='redis://localhost:6379/0')
    def test_redis_cache_passes_when_url_set(self, _mock_redis):
        from pinova_backend.core.checks import check_redis_cache_in_production

        errors = check_redis_cache_in_production(None)
        self.assertEqual(errors, [])
