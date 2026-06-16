"""Vue refresh JWT — remplace celle de dj-rest-auth (sérialiseur Fotoce)."""

from rest_framework import permissions
from dj_rest_auth.jwt_auth import get_refresh_view

from .jwt_serializers import FotoceCookieTokenRefreshSerializer


def get_fotoce_refresh_view():
    """Même CBV que dj-rest-auth (cookies), avec gestion user introuvable."""
    base = get_refresh_view()

    class FotoceTokenRefreshView(base):
        serializer_class = FotoceCookieTokenRefreshSerializer
        permission_classes = [permissions.AllowAny]

    return FotoceTokenRefreshView
