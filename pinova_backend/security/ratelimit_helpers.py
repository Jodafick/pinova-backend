"""Helpers django-ratelimit compatibles DRF."""

from __future__ import annotations

from django.conf import settings
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit


def normalize_ratelimit_rate(rate: str) -> str:
    """Convertit « 10/minute » (DRF) en « 10/m » (django-ratelimit)."""
    raw = (rate or '').strip().lower()
    replacements = (
        ('/minute', '/m'),
        ('/min', '/m'),
        ('/second', '/s'),
        ('/sec', '/s'),
        ('/hour', '/h'),
        ('/day', '/d'),
    )
    for old, new in replacements:
        raw = raw.replace(old, new)
    return raw


def get_ratelimit_rate(setting_name: str, default: str) -> str:
    return normalize_ratelimit_rate(getattr(settings, setting_name, default))


def ratelimit_post(*, group: str, setting_name: str, default: str, key='ip'):
    rate = get_ratelimit_rate(setting_name, default)
    return method_decorator(
        ratelimit(key=key, rate=rate, method='POST', block=True, group=group),
        name='post',
    )


def ratelimit_dispatch(*, group: str, setting_name: str, default: str, key='ip', method='POST'):
    rate = get_ratelimit_rate(setting_name, default)
    return method_decorator(
        ratelimit(key=key, rate=rate, method=method, block=True, group=group),
        name='dispatch',
    )
