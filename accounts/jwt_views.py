"""Vue refresh JWT — remplace celle de dj-rest-auth (sérialiseur Pinova)."""

from dj_rest_auth.jwt_auth import get_refresh_view

from .jwt_serializers import PinovaCookieTokenRefreshSerializer


def get_pinova_refresh_view():
    """Même CBV que dj-rest-auth (cookies), avec gestion user introuvable."""
    base = get_refresh_view()

    class PinovaTokenRefreshView(base):
        serializer_class = PinovaCookieTokenRefreshSerializer

    return PinovaTokenRefreshView
