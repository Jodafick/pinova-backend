"""Gestion du cache Django (Redis partagé vs LocMem) et avertissements prod."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger('pinova.cache')


def redis_url_from_env() -> str:
    return (os.environ.get('REDIS_URL') or os.environ.get('PINNOVA_REDIS_URL') or '').strip()


def build_caches_config(*, redis_url: str, debug: bool) -> dict:
    if redis_url:
        return {
            'default': {
                'BACKEND': 'django_redis.cache.RedisCache',
                'LOCATION': redis_url,
                'OPTIONS': {
                    'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                },
                'TIMEOUT': 120,
            }
        }
    return {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'pinova-default',
            'TIMEOUT': 120,
        }
    }


def warn_if_locmem_in_production(*, redis_url: str, debug: bool) -> None:
    if redis_url or debug:
        return
    logger.warning(
        'REDIS_URL absent : cache LocMem actif — throttling DRF / django-ratelimit '
        'NON partagé entre workers Gunicorn/uWSGI. Définissez REDIS_URL en production.'
    )
