"""Middleware Sentry — signale les requêtes API > 1s (alerte p95 côté Sentry Performance)."""
from __future__ import annotations

import time

from django.conf import settings

from pinova_backend.observability.sentry import capture_slow_api


class SentryApiTimingMiddleware:
    SLOW_MS = 1000

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not (getattr(settings, 'SENTRY_DSN', '') or '').strip():
            return self.get_response(request)

        path = request.path or ''
        if not path.startswith('/api/'):
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        if duration_ms >= self.SLOW_MS:
            capture_slow_api(
                method=request.method,
                path=path,
                status_code=getattr(response, 'status_code', 0),
                duration_ms=duration_ms,
            )
        return response
