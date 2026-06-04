"""
Tests des endpoints dj-rest-auth sous /api/auth/ (login, reset mot de passe, refresh).
Alignés avec le client mobile / web (JWT, PinovaLoginSerializer).
"""
from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.serializers import PinovaLoginSerializer

try:
    from allauth.account.models import EmailAddress
except ImportError:  # pragma: no cover
    EmailAddress = None


def _ensure_verified_email(user: User):
    if EmailAddress is None:
        return
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email.lower(),
        defaults={'primary': True, 'verified': True},
    )


class AuthLoginApiTests(APITestCase):
    """POST /api/auth/login/"""

    def setUp(self):
        self.url = '/api/auth/login/'
        self.password = 'password123'
        self.user = User.objects.create_user(
            username='apitester',
            email='apitester@example.com',
            password=self.password,
        )
        _ensure_verified_email(self.user)

    def test_login_success_returns_jwt(self):
        r = self.client.post(
            self.url,
            {'email': 'apitester@example.com', 'password': self.password},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertIn('access', r.data)
        self.assertIn('refresh', r.data)

    def test_login_unknown_email_field_error(self):
        r = self.client.post(
            self.url,
            {'email': 'nobody@example.com', 'password': self.password},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', r.data)
        self.assertEqual(r.data['email'][0], PinovaLoginSerializer.CODE_UNKNOWN_EMAIL)

    def test_login_wrong_password_field_error(self):
        r = self.client.post(
            self.url,
            {'email': 'apitester@example.com', 'password': 'wrong-pass'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', r.data)
        self.assertEqual(r.data['password'][0], PinovaLoginSerializer.CODE_WRONG_PASSWORD)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='pinova-tests@localhost',
)
class AuthPasswordResetApiTests(APITestCase):
    """POST /api/auth/password/reset/ — ne doit pas renvoyer 500 si l’e-mail est configuré."""

    def setUp(self):
        self.url = '/api/auth/password/reset/'
        User.objects.create_user(
            username='resetuser',
            email='resetuser@example.com',
            password='password123',
        )

    def test_password_reset_existing_email_returns_ok(self):
        r = self.client.post(
            self.url,
            {'email': 'resetuser@example.com'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertGreaterEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        combined = msg.body or ''
        for alt, _ctype in getattr(msg, 'alternatives', None) or []:
            combined += alt or ''
        self.assertIn('/password-reset-confirm/', combined)

    def test_password_reset_unknown_email_still_ok(self):
        """API ne révèle pas si l’e-mail existe (comportement habituel dj-rest-auth / allauth)."""
        r = self.client.post(
            self.url,
            {'email': 'ghost@example.com'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)


class AuthTokenRefreshApiTests(APITestCase):
    """POST /api/auth/token/refresh/"""

    def setUp(self):
        self.login_url = '/api/auth/login/'
        self.refresh_url = '/api/auth/token/refresh/'
        self.password = 'password123'
        self.user = User.objects.create_user(
            username='refreshuser',
            email='refreshuser@example.com',
            password=self.password,
        )
        _ensure_verified_email(self.user)

    def test_refresh_with_valid_refresh_token(self):
        login = self.client.post(
            self.login_url,
            {'email': 'refreshuser@example.com', 'password': self.password},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        refresh = login.data.get('refresh')
        self.assertTrue(refresh)
        r = self.client.post(self.refresh_url, {'refresh': refresh}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertIn('access', r.data)

    def test_refresh_returns_401_when_user_deleted(self):
        login = self.client.post(
            self.login_url,
            {'email': 'refreshuser@example.com', 'password': self.password},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        refresh = login.data.get('refresh')
        self.user.delete()
        r = self.client.post(self.refresh_url, {'refresh': refresh}, format='json')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED, r.content)
