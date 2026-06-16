"""Checks Django deploy — production durcie."""

from django.conf import settings
from django.core.checks import Error, register, Tags

from fotoce_backend.config.cache import redis_url_from_env


@register(Tags.security, deploy=True)
def check_debug_disabled_for_production(app_configs, **kwargs):
    if settings.DEBUG:
        return [
            Error(
                'DEBUG=True est interdit en déploiement production. '
                'Définissez DEBUG=False (ou DEBUG=0) dans l’environnement.',
                id='fotoce.E001',
            ),
        ]
    return []


@register(Tags.security, deploy=True)
def check_secret_key_not_dev_default(app_configs, **kwargs):
    dev_key = 'django-insecure-dev-only-change-me-not-for-production'
    if settings.SECRET_KEY == dev_key:
        return [
            Error(
                'SECRET_KEY/DJANGO_SECRET_KEY utilise la valeur de développement. '
                'Générez une clé forte pour la production.',
                id='fotoce.E002',
            ),
        ]
    return []


@register(Tags.security, deploy=True)
def check_redis_channel_layer_in_production(app_configs, **kwargs):
    """Channels multi-worker : Redis obligatoire en production."""
    if settings.DEBUG:
        return []
    backend = settings.CHANNEL_LAYERS.get('default', {}).get('BACKEND', '')
    if 'InMemory' in backend:
        return [
            Error(
                'CHANNEL_LAYERS utilise InMemoryChannelLayer en production. '
                'Définissez REDIS_URL (ou PINNOVA_REDIS_URL) pour le broadcast multi-worker.',
                id='fotoce.E003',
            ),
        ]
    redis_url = redis_url_from_env()
    if not redis_url:
        return [
            Error(
                'REDIS_URL absent en production — requis pour CHANNEL_LAYERS (WebSockets multi-worker).',
                id='fotoce.E004',
            ),
        ]
    return []


@register(Tags.security, deploy=True)
def check_redis_cache_in_production(app_configs, **kwargs):
    """Cache partagé : Redis obligatoire en production (throttle DRF / OTP / ratelimit)."""
    if settings.DEBUG:
        return []
    backend = settings.CACHES.get('default', {}).get('BACKEND', '')
    if 'locmem' in backend.lower() or 'LocMem' in backend:
        return [
            Error(
                'CACHES utilise LocMem en production. '
                'Définissez REDIS_URL pour un cache partagé entre workers Gunicorn.',
                id='fotoce.E005',
            ),
        ]
    redis_url = redis_url_from_env()
    if not redis_url:
        return [
            Error(
                'REDIS_URL absent en production — requis pour le cache partagé (throttling, OTP, sessions).',
                id='fotoce.E006',
            ),
        ]
    return []


@register(Tags.security, deploy=True)
def check_fedapay_webhook_secret_in_production(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    secret = (getattr(settings, 'FEDAPAY_WEBHOOK_SECRET', None) or '').strip()
    if not secret:
        return [
            Error(
                'FEDAPAY_WEBHOOK_SECRET absent en production — requis pour valider les webhooks FedaPay.',
                id='fotoce.E007',
            ),
        ]
    return []


@register(Tags.security, deploy=True)
def check_media_signing_secret_in_production(app_configs, **kwargs):
    """Évite de réutiliser SECRET_KEY pour les URLs médias signées."""
    if settings.DEBUG:
        return []
    import os

    explicit = (os.environ.get('MEDIA_SIGNING_SECRET') or '').strip()
    if not explicit:
        return [
            Error(
                'MEDIA_SIGNING_SECRET doit être défini explicitement en production '
                '(ne pas réutiliser DJANGO_SECRET_KEY pour les signatures médias).',
                id='fotoce.E008',
            ),
        ]
    return []


@register(Tags.security, deploy=True)
def check_jwt_httponly_in_production(app_configs, **kwargs):
    if settings.DEBUG:
        return []
    rest_auth = getattr(settings, 'REST_AUTH', {}) or {}
    if not rest_auth.get('JWT_AUTH_HTTPONLY'):
        return [
            Error(
                'JWT_AUTH_HTTPONLY doit être activé en production (JWT_AUTH_HTTPONLY=1) '
                '— refresh token uniquement en cookie HttpOnly.',
                id='fotoce.E009',
            ),
        ]
    return []
