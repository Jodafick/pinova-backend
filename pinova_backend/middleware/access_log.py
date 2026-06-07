"""Middleware access log JSON — prod uniquement."""
from __future__ import annotations

import time

from django.conf import settings

from pinova_backend.observability.logging import log_http_access


class StructuredAccessLogMiddleware:
    """Log une ligne JSON par requête HTTP (hors health/static en prod)."""

    SKIP_PREFIXES = ('/static/', '/media/', '/admin/jsi18n', '/api/health')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG:
            return self.get_response(request)

        path = request.path or ''
        if path.startswith(self.SKIP_PREFIXES):
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        latency_ms = (time.perf_counter() - start) * 1000

        user_id = None
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            user_id = getattr(user, 'id', None)

        request_id = getattr(request, 'request_id', None) or 'unknown'

        log_http_access(
            request_id=request_id,
            user_id=user_id,
            path=path,
            method=request.method,
            latency_ms=latency_ms,
            status=getattr(response, 'status_code', 0),
        )
        return response
