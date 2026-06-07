"""Throttle DRF pour webhooks externes (complète django-ratelimit)."""

from __future__ import annotations

from pinova_backend.security.throttling import IPThrottleMixin
from rest_framework.throttling import SimpleRateThrottle


class WebhookIPThrottle(SimpleRateThrottle, IPThrottleMixin):
    scope = 'webhook'

    def get_cache_key(self, request, view):
        return IPThrottleMixin.get_cache_key(self, request, view)
