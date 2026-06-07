"""Tests health checks + corrélation X-Request-ID."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


def _mock_checks(*, db_ok=True, redis_ok=True, broker_ok=True, fedapay_ok=True):
    return {
        'db': {'ok': db_ok, 'detail': 'ok', 'latency_ms': 1.0},
        'redis': {'ok': redis_ok, 'detail': 'ok', 'latency_ms': 1.0},
        'celery': {
            'ok': broker_ok,
            'broker': {'ok': broker_ok, 'detail': 'ok'},
            'workers': {'ok': True, 'detail': 'ok', 'count': 1},
            'always_eager': False,
            'beat_schedule': [],
        },
        'fedapay': {'ok': fedapay_ok, 'detail': 'ok', 'latency_ms': 10.0},
    }


@override_settings(DEBUG=False)
class HealthViewTests(SimpleTestCase):
    def test_health_ok(self):
        with patch('pinova_backend.health.views._collect_checks', return_value=_mock_checks()):
            response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('db', data['checks'])

    def test_health_db_down(self):
        with patch(
            'pinova_backend.health.views._collect_checks',
            return_value=_mock_checks(db_ok=False),
        ):
            response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'degraded')


@override_settings(DEBUG=False)
class HealthReadyViewTests(SimpleTestCase):
    def test_ready_when_dependencies_ok(self):
        with patch('pinova_backend.health.views._collect_checks', return_value=_mock_checks()):
            response = self.client.get(reverse('health-ready'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ready')

    def test_not_ready_when_db_down(self):
        with patch(
            'pinova_backend.health.views._collect_checks',
            return_value=_mock_checks(db_ok=False),
        ):
            response = self.client.get(reverse('health-ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'not_ready')

    def test_not_ready_when_broker_down(self):
        with patch(
            'pinova_backend.health.views._collect_checks',
            return_value=_mock_checks(broker_ok=False),
        ):
            response = self.client.get(reverse('health-ready'))
        self.assertEqual(response.status_code, 503)


class RequestIdMiddlewareTests(SimpleTestCase):
    def test_echoes_incoming_request_id(self):
        incoming = 'test-req-abc-123'
        response = self.client.get(reverse('health'), HTTP_X_REQUEST_ID=incoming)
        self.assertEqual(response.headers.get('X-Request-ID'), incoming)

    def test_generates_request_id_when_missing(self):
        response = self.client.get(reverse('health'))
        rid = response.headers.get('X-Request-ID')
        self.assertTrue(rid)
        self.assertGreater(len(rid), 8)
