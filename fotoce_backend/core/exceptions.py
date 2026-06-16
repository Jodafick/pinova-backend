"""Exception handler DRF — inclut django-ratelimit."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

try:
    from django_ratelimit.exceptions import Ratelimited
except ImportError:  # pragma: no cover
    Ratelimited = None  # type: ignore[misc, assignment]


def fotoce_exception_handler(exc, context):
    if Ratelimited is not None and isinstance(exc, Ratelimited):
        return Response(
            {'detail': 'Too many requests. Please try again later.', 'code': 'fotoce_rate_limited'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    return exception_handler(exc, context)
