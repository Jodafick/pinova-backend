"""Configuration CHANNEL_LAYERS — Redis résilient (keepalive, health check, retry)."""

from __future__ import annotations

_REDIS_CONN_KWARGS = {
    'socket_keepalive': True,
    'retry_on_timeout': True,
    'health_check_interval': 15,
    'socket_connect_timeout': 10,
    # BRPOP channels_redis = 5 s ; marge pour éviter TimeoutError socket prématuré.
    'socket_timeout': 10,
}

_RESILIENT_BACKEND = 'fotoce_backend.config.redis_channel_layer.ResilientRedisChannelLayer'


def _redis_host_entry(redis_url: str) -> dict:
    return {'address': redis_url, **_REDIS_CONN_KWARGS}


def build_channel_layers_config(*, redis_url: str) -> dict:
    if not redis_url:
        return {
            'default': {
                'BACKEND': 'channels.layers.InMemoryChannelLayer',
            },
        }
    return {
        'default': {
            'BACKEND': _RESILIENT_BACKEND,
            'CONFIG': {
                'hosts': [_redis_host_entry(redis_url)],
                'capacity': 1500,
                'expiry': 10,
                'group_expiry': 3600,
            },
        },
    }
