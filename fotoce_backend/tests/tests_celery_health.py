"""Tests health check Celery."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class CeleryHealthViewTests(SimpleTestCase):
    def test_health_eager_mode(self):
        with patch('fotoce_backend.health.views._broker_ping', return_value=(True, 'ok')):
            response = self.client.get(reverse('health-celery'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['broker']['ok'])
        self.assertTrue(data['always_eager'])
        self.assertIn('pins-publish-scheduled', data['beat_schedule'])

    def test_health_broker_down(self):
        with patch('fotoce_backend.health.views._broker_ping', return_value=(False, 'connection refused')):
            response = self.client.get(reverse('health-celery'))
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['broker']['ok'])


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class CeleryTaskRegistrationTests(SimpleTestCase):
    def test_beat_tasks_registered(self):
        import accounts.tasks  # noqa: F401
        import fotos.tasks  # noqa: F401
        import referrals.tasks  # noqa: F401
        from fotoce_backend.celery import app

        names = {
            'fotos.send_weekly_pro_digest',
            'fotos.purge_expired_ephemeral_stories',
            'fotos.publish_scheduled_fotos',
            'accounts.enforce_subscriptions_due',
            'accounts.purge_scheduled_account_deletions',
            'referrals.referral_reward_scan',
            'referrals.referral_retention_scan',
        }
        registered = set(app.tasks.keys())
        missing = names - registered
        self.assertFalse(missing, f'missing tasks: {missing}')

    def test_fotoce_task_retry_policy(self):
        from fotoce_backend.celery import FotoceTask

        self.assertEqual(FotoceTask.max_retries, 3)
        self.assertTrue(FotoceTask.retry_backoff)
