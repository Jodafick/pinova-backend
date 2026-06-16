"""Auth DRF — JWT optionnel pour les endpoints publics (invités avec token périmé en localStorage)."""

from __future__ import annotations

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class OptionalJWTAuthentication(JWTAuthentication):
    """
    Comme JWTAuthentication, mais un Bearer invalide ou expiré ne renvoie pas 401 :
    la requête continue en anonyme (AllowAny peut alors répondre).
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except AuthenticationFailed:
            return None
