"""Tests configuration CHANNEL_LAYERS résiliente."""
from django.test import SimpleTestCase

from fotoce_backend.config.channel_layers import build_channel_layers_config


class ChannelLayersConfigTests(SimpleTestCase):
    def test_inmemory_when_no_redis_url(self):
        cfg = build_channel_layers_config(redis_url='')
        self.assertEqual(
            cfg['default']['BACKEND'],
            'channels.layers.InMemoryChannelLayer',
        )

    def test_resilient_redis_backend_when_url_set(self):
        cfg = build_channel_layers_config(redis_url='redis://localhost:6379/0')
        self.assertEqual(
            cfg['default']['BACKEND'],
            'fotoce_backend.config.redis_channel_layer.ResilientRedisChannelLayer',
        )
        hosts = cfg['default']['CONFIG']['hosts']
        self.assertEqual(hosts[0]['address'], 'redis://localhost:6379/0')
        self.assertTrue(hosts[0]['socket_keepalive'])
        self.assertTrue(hosts[0]['retry_on_timeout'])
        self.assertEqual(hosts[0]['health_check_interval'], 15)
