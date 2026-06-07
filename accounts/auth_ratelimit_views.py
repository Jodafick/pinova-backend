"""Vues auth dj-rest-auth avec django-ratelimit (IP)."""

from dj_rest_auth.views import LoginView, PasswordResetConfirmView, PasswordResetView

from pinova_backend.security.ratelimit_helpers import ratelimit_post


@ratelimit_post(group='auth_login', setting_name='API_RATELIMIT_LOGIN', default='10/minute')
class PinovaLoginView(LoginView):
    """POST /api/auth/login/ — quota IP partagé via cache Redis."""


@ratelimit_post(group='auth_password_reset', setting_name='API_RATELIMIT_PASSWORD_RESET', default='5/minute')
class PinovaPasswordResetView(PasswordResetView):
    """POST /api/auth/password/reset/ — anti-abus e-mail."""


@ratelimit_post(
    group='auth_password_reset_confirm',
    setting_name='API_RATELIMIT_PASSWORD_RESET',
    default='5/minute',
)
class PinovaPasswordResetConfirmView(PasswordResetConfirmView):
    """POST /api/auth/password/reset/confirm/ — anti brute-force token."""
