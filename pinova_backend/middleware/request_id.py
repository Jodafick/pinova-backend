"""Middleware X-Request-ID — corrélation front → backend → Sentry."""
from __future__ import annotations

import uuid

from pinova_backend.core.request_context import clear_request_context, set_request_context


class RequestIdMiddleware:
    HEADER = 'X-Request-ID'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = (request.headers.get(self.HEADER) or request.META.get('HTTP_X_REQUEST_ID') or '').strip()
        request_id = incoming or str(uuid.uuid4())
        request.request_id = request_id
        set_request_context(request_id=request_id)

        try:
            import sentry_sdk

            sentry_sdk.set_tag('request_id', request_id)
        except Exception:
            pass

        response = self.get_response(request)
        response[self.HEADER] = request_id
        clear_request_context()
        return response
