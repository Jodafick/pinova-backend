"""Tests sécurité OTP (tentatives, lockout, resend)."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import EmailOTP
from accounts.otp_security import MAX_VERIFY_ATTEMPTS, clear_verify_security

try:
    from allauth.account.models import EmailAddress
except ImportError:  # pragma: no cover
    EmailAddress = None


def _ensure_user(email: str, password: str = 'Fotoce2026!') -> User:
    user = User.objects.create_user(username=email.split('@')[0], email=email, password=password)
    if EmailAddress is not None:
        EmailAddress.objects.update_or_create(
            user=user,
            email=email.lower(),
            defaults={'primary': True, 'verified': False},
        )
    otp = EmailOTP.objects.create(
        user=user,
        otp_code='123456',
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    otp.save()
    clear_verify_security(email)
    cache.clear()
    return user


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='fotoce-tests@localhost',
)
class OtpVerifySecurityTests(APITestCase):
    verify_url = '/api/verify-otp/'

    def setUp(self):
        cache.clear()
        self.email = 'otpuser@example.com'
        self.user = _ensure_user(self.email)

    def test_wrong_code_returns_generic_error_and_attempts_remaining(self):
        r = self.client.post(
            self.verify_url,
            {'email': self.email, 'otp': '000000'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('attempts_remaining', r.data)
        self.assertEqual(r.data['attempts_remaining'], MAX_VERIFY_ATTEMPTS - 1)
        self.user.email_otp.refresh_from_db()
        self.assertEqual(self.user.email_otp.failed_attempts, 1)

    def test_lockout_after_max_attempts(self):
        for _ in range(MAX_VERIFY_ATTEMPTS):
            self.client.post(
                self.verify_url,
                {'email': self.email, 'otp': '000000'},
                format='json',
            )
        r = self.client.post(
            self.verify_url,
            {'email': self.email, 'otp': '000000'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(r.data.get('code'), 'fotoce_otp_locked')
        self.assertIn('retry_after_seconds', r.data)

    def test_unknown_email_same_generic_shape(self):
        r = self.client.post(
            self.verify_url,
            {'email': 'ghost@example.com', 'otp': '123456'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('attempts_remaining', r.data)
        self.assertIn('Code invalide', r.data['error'])

    def test_valid_code_clears_lockout_state(self):
        r = self.client.post(
            self.verify_url,
            {'email': self.email, 'otp': '123456'},
            format='json',
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('access', r.data)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='fotoce-tests@localhost',
)
class OtpResendSecurityTests(APITestCase):
    resend_url = '/api/resend-otp/'

    def setUp(self):
        cache.clear()
        self.email = 'resend@example.com'
        _ensure_user(self.email)

    def test_resend_cooldown(self):
        r1 = self.client.post(self.resend_url, {'email': self.email}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        r2 = self.client.post(self.resend_url, {'email': self.email}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(r2.data.get('code'), 'fotoce_otp_resend_cooldown')

    def test_resend_unknown_email_still_ok(self):
        r = self.client.post(self.resend_url, {'email': 'nobody@example.com'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('message', r.data)
        self.assertEqual(len(mail.outbox), 0)
