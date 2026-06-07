"""
Tests modes de panne — Redis, FedaPay, SMTP, chaos health/ready.

Exécution :
  cd pinova-backend && python manage.py test pinova_backend.tests_failure_modes -v 2
"""
from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.mail_delivery import EMAIL_DELIVERY_ERROR_CODE, EmailDeliveryUnavailable
from accounts.models import DataExportJob, EmailOTP, Profile, SubscriptionPricing
from accounts.otp_security import lockout_status, resend_cooldown_remaining
from monetization.fedapay_client import FEDAPAY_CIRCUIT, CircuitOpenError
from pinova_backend.websocket.ratelimit import allow_ws_connection

INVALID_REDIS_CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:59999/0',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 0.3,
            'SOCKET_TIMEOUT': 0.3,
        },
        'TIMEOUT': 120,
    }
}

CRITICAL_BEAT_KEYS = (
    'pins-send-weekly-pro-digest',
    'pins-purge-ephemeral-stories',
    'pins-publish-scheduled',
    'accounts-enforce-subscriptions',
    'accounts-purge-deletions',
    'referrals-reward-scan',
    'referrals-retention-scan',
    'accounts-discovery-streak-reminder',
    'accounts-reactivation-j7-email',
    'accounts-reactivation-j30-email',
    'pins-reindex-typesense-nightly',
)


def _mock_checks(*, db_ok=True, redis_ok=True, broker_ok=True, fedapay_ok=True, redis_detail='ok'):
    return {
        'db': {'ok': db_ok, 'detail': 'ok', 'latency_ms': 1.0},
        'redis': {'ok': redis_ok, 'detail': redis_detail, 'latency_ms': 1.0},
        'celery': {
            'ok': broker_ok,
            'broker': {'ok': broker_ok, 'detail': 'ok'},
            'workers': {'ok': True, 'detail': 'ok', 'count': 1},
            'always_eager': False,
            'beat_schedule': list(CRITICAL_BEAT_KEYS),
        },
        'fedapay': {'ok': fedapay_ok, 'detail': 'ok', 'latency_ms': 10.0},
    }


@override_settings(DEBUG=False, PINNOVA_SHARED_CACHE=True)
class RedisReadyFailureTests(SimpleTestCase):
    def test_not_ready_when_redis_down(self):
        with patch(
            'pinova_backend.health.views._collect_checks',
            return_value=_mock_checks(redis_ok=False, redis_detail='connection refused'),
        ):
            response = self.client.get(reverse('health-ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'not_ready')
        self.assertFalse(response.json()['checks']['redis']['ok'])


@override_settings(
    DEBUG=False,
    PINNOVA_SHARED_CACHE=True,
    CACHES=INVALID_REDIS_CACHES,
    CELERY_TASK_ALWAYS_EAGER=True,
)
class RedisChaosHealthTests(TestCase):
    """Chaos : REDIS_URL configuré mais Redis injoignable → readiness 503."""

    @patch('pinova_backend.health.views._broker_ping', return_value=(True, 'ok'))
    @patch('pinova_backend.health.views._check_fedapay', return_value={'ok': True, 'detail': 'ok', 'latency_ms': 1.0})
    def test_health_reports_redis_failure(self, _fedapay, _broker):
        response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['checks']['redis']['ok'])
        self.assertEqual(data['status'], 'degraded')

    @patch('pinova_backend.health.views._broker_ping', return_value=(True, 'ok'))
    @patch('pinova_backend.health.views._check_fedapay', return_value={'ok': True, 'detail': 'ok', 'latency_ms': 1.0})
    def test_ready_returns_503_when_redis_unreachable(self, _fedapay, _broker):
        response = self.client.get(reverse('health-ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'not_ready')
        self.assertFalse(response.json()['checks']['redis']['ok'])


class RedisGracefulDegradeTests(SimpleTestCase):
    def test_otp_lockout_fail_open_when_cache_raises(self):
        with patch('accounts.otp_security.cache.get', side_effect=ConnectionError('redis down')):
            locked, remaining = lockout_status('user@example.com')
        self.assertFalse(locked)
        self.assertEqual(remaining, 0)

    def test_otp_resend_cooldown_fail_open_when_cache_raises(self):
        with patch('accounts.otp_security.cache.get', side_effect=ConnectionError('redis down')):
            cooldown = resend_cooldown_remaining('user@example.com')
        self.assertEqual(cooldown, 0)

    def test_ws_connection_fail_open_when_cache_raises(self):
        scope = {'client': ('127.0.0.1', 12345), 'headers': []}
        with patch('pinova_backend.websocket.ratelimit.cache.get', side_effect=ConnectionError('redis down')):
            self.assertTrue(allow_ws_connection(scope, namespace='leaderboard'))


class CriticalBeatScheduleTests(SimpleTestCase):
    def test_all_critical_beat_tasks_registered(self):
        import accounts.tasks  # noqa: F401
        import pins.search.tasks  # noqa: F401
        import pins.tasks  # noqa: F401
        import referrals.tasks  # noqa: F401
        from pinova_backend.celery import app

        schedule = app.conf.beat_schedule or {}
        missing = [key for key in CRITICAL_BEAT_KEYS if key not in schedule]
        self.assertFalse(missing, f'beat keys manquantes: {missing}')

        task_names = {
            schedule[key]['task'] for key in CRITICAL_BEAT_KEYS if key in schedule
        }
        registered = set(app.tasks.keys())
        missing_tasks = task_names - registered
        self.assertFalse(missing_tasks, f'tasks Celery non enregistrées: {missing_tasks}')


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='pinova-tests@localhost',
)
class SmtpDownApiTests(APITestCase):
    def test_register_returns_email_delivery_unavailable(self):
        payload = {
            'email': 'newuser@example.com',
            'password1': 'Str0ngPass!pinova',
            'password2': 'Str0ngPass!pinova',
        }
        with patch('accounts.serializers.send_pinova_mail', side_effect=EmailDeliveryUnavailable('smtp down')):
            response = self.client.post('/api/register/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(EMAIL_DELIVERY_ERROR_CODE, response.data.get('code', []))

    def test_resend_otp_returns_email_delivery_unavailable(self):
        try:
            from allauth.account.models import EmailAddress
        except ImportError:
            self.skipTest('allauth absent')
        user = User.objects.create_user('otpuser', 'otpuser@example.com', 'Str0ngPass!pinova')
        EmailAddress.objects.create(user=user, email=user.email, verified=False, primary=True)
        EmailOTP.objects.create(user=user, expires_at=timezone.now() + timedelta(minutes=10))
        with patch('accounts.views.send_pinova_mail', side_effect=EmailDeliveryUnavailable('smtp down')):
            response = self.client.post('/api/resend-otp/', {'email': user.email}, format='json')
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data.get('code'), EMAIL_DELIVERY_ERROR_CODE)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ExportEmailFailureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('exportfail', 'exportfail@example.com', 'Str0ngPass!pinova')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('accounts.gdpr_views.send_pinova_mail', side_effect=EmailDeliveryUnavailable('smtp down'))
    def test_export_job_completes_when_ready_email_unavailable(self, _mock_mail):
        response = self.client.post('/api/account/export-data/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        job = DataExportJob.objects.get(user=self.user)
        self.assertEqual(job.status, DataExportJob.STATUS_READY)
        self.assertTrue(job.file_path)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='pinova-tests@localhost',
)
class FedapayCircuitOpenCheckoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('payer', 'payer@example.com', 'Str0ngPass!pinova')
        self.client.force_authenticate(user=self.user)
        for plan in (Profile.PLAN_PLUS, Profile.PLAN_PRO):
            SubscriptionPricing.objects.create(
                plan=plan,
                billing_cycle=SubscriptionPricing.BILLING_MONTHLY,
                seat_bundle=SubscriptionPricing.SEAT_SOLO,
                amount=2500,
                duration_days=30,
                currency_iso='XOF',
                is_active=True,
            )

    @patch.dict(os.environ, {'FEDAPAY_SECRET_KEY': 'sk_test_failure_mode'})
    @patch('monetization.fedapay_client.fedapay_post')
    def test_subscription_checkout_returns_readable_503_not_500(self, mock_post):
        mock_post.side_effect = CircuitOpenError('fedapay circuit open')
        response = self.client.post(
            '/api/subscription/checkout/',
            {'plan': 'plus', 'billing_cycle': 'monthly'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data.get('error'), 'FedaPay temporarily unavailable')
        self.assertNotEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @patch.dict(os.environ, {'FEDAPAY_SECRET_KEY': 'sk_test_failure_mode'})
    def test_subscription_checkout_after_circuit_tripped(self):
        FEDAPAY_CIRCUIT.record_success()
        for _ in range(5):
            FEDAPAY_CIRCUIT.record_failure()
        self.assertTrue(FEDAPAY_CIRCUIT.is_open())
        with patch('monetization.fedapay_client.fedapay_post', side_effect=CircuitOpenError('fedapay circuit open')):
            response = self.client.post(
                '/api/subscription/checkout/',
                {'plan': 'pro', 'billing_cycle': 'monthly'},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('FedaPay', response.data.get('error', ''))
        FEDAPAY_CIRCUIT.record_success()
