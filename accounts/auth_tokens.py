"""Émission JWT après vérification OTP (session auto sans re-login)."""

from __future__ import annotations

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer


def build_jwt_auth_payload(user, request=None, *, message: str | None = None) -> dict:
    refresh = RefreshToken.for_user(user)
    ctx = {'request': request} if request is not None else {}
    return {
        'message': message or 'Email validé avec succès',
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserSerializer(user, context=ctx).data,
    }


def _is_mobile_checkout_request(request) -> bool:
    if request is None:
        return False
    data = getattr(request, 'data', None) or {}
    platform = str(data.get('return_platform') or data.get('client_platform') or '').strip().lower()
    if platform in ('mobile', 'app', 'ios', 'android'):
        return True
    hdr = ''
    try:
        hdr = str(request.META.get('HTTP_X_PINOVA_CLIENT', '')).strip().lower()
    except Exception:
        pass
    return hdr in ('mobile', 'app', 'ios', 'android')


def checkout_return_url(flow: str, *, request=None) -> str:
    """URL de retour FedaPay → page succès (web ou deep link mobile)."""
    if _is_mobile_checkout_request(request):
        scheme = str(getattr(settings, 'MOBILE_APP_SCHEME', 'pinova')).strip().rstrip(':') or 'pinova'
        return f'{scheme}://checkout/return?flow={flow}'
    base = str(settings.FRONTEND_URL).rstrip('/')
    return f'{base}/checkout/return?flow={flow}'
