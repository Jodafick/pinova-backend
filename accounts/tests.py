import hashlib
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import MobileOAuthLoginCode


def mobile_oauth_code_hash(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode('utf-8')).hexdigest()


class MobileGoogleSessionExchangeTests(APITestCase):
    def setUp(self):
        self.url = reverse('mobile_google_session_exchange')
        self.raw_code = 'pinova-mobile-oauth-code'
        self.mobile_state = 'pinova-mobile-oauth-state'
        self.device_binding_id = 'pb_device_123'
        self.payload = {'access': 'jwt-access', 'refresh': 'jwt-refresh'}
        self.login_code = MobileOAuthLoginCode.objects.create(
            code_hash=mobile_oauth_code_hash(self.raw_code),
            device_binding_id=self.device_binding_id,
            mobile_state_hash=mobile_oauth_code_hash(self.mobile_state),
            payload=self.payload,
            expires_at=timezone.now() + timedelta(minutes=2),
        )

    def test_exchange_consumes_code_when_device_binding_matches(self):
        response = self.client.post(
            self.url,
            {'code': self.raw_code, 'mobile_state': self.mobile_state},
            format='json',
            HTTP_X_PINOVA_DEVICE_BINDING=self.device_binding_id,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.payload)
        self.login_code.refresh_from_db()
        self.assertIsNotNone(self.login_code.consumed_at)
        self.assertEqual(self.login_code.payload, {})

    def test_exchange_rejects_missing_device_binding_header_without_consuming_code(self):
        response = self.client.post(
            self.url,
            {'code': self.raw_code, 'mobile_state': self.mobile_state},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.login_code.refresh_from_db()
        self.assertIsNone(self.login_code.consumed_at)
        self.assertEqual(self.login_code.payload, self.payload)

    def test_exchange_rejects_mismatched_device_binding_without_consuming_code(self):
        response = self.client.post(
            self.url,
            {'code': self.raw_code, 'mobile_state': self.mobile_state},
            format='json',
            HTTP_X_PINOVA_DEVICE_BINDING='pb_attacker_device',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.login_code.refresh_from_db()
        self.assertIsNone(self.login_code.consumed_at)
        self.assertEqual(self.login_code.payload, self.payload)

    def test_exchange_rejects_mismatched_mobile_state_without_consuming_code(self):
        response = self.client.post(
            self.url,
            {'code': self.raw_code, 'mobile_state': 'attacker-state'},
            format='json',
            HTTP_X_PINOVA_DEVICE_BINDING=self.device_binding_id,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.login_code.refresh_from_db()
        self.assertIsNone(self.login_code.consumed_at)
        self.assertEqual(self.login_code.payload, self.payload)
