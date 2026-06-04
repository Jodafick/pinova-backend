"""JWT SimpleJWT — comportements Pinova."""

from django.contrib.auth import get_user_model
from dj_rest_auth.jwt_auth import CookieTokenRefreshSerializer
from rest_framework.exceptions import AuthenticationFailed


class PinovaCookieTokenRefreshSerializer(CookieTokenRefreshSerializer):
    """
    Refresh (dj-rest-auth) : user supprimé / BDD réinitialisée → 401, pas DoesNotExist (500).
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist:
            raise AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            ) from None
