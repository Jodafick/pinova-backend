"""Tests résilience — circuit breaker, retry, logs structurés."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from pinova_backend.security.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    ExternalRetryableError,
    external_call,
    log_external_call,
)


class CircuitBreakerTests(SimpleTestCase):
    def test_opens_after_threshold(self):
        breaker = CircuitBreaker('test', failure_threshold=3, recovery_timeout=60.0)
        for _ in range(3):
            breaker.record_failure()
        self.assertTrue(breaker.is_open())

    def test_success_resets(self):
        breaker = CircuitBreaker('test', failure_threshold=3, recovery_timeout=60.0)
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        self.assertFalse(breaker.is_open())

    def test_external_call_raises_when_open(self):
        breaker = CircuitBreaker('test', failure_threshold=1, recovery_timeout=60.0)
        breaker.record_failure()

        with self.assertRaises(CircuitOpenError):
            external_call(
                service='test',
                operation='ping',
                fn=lambda: True,
                circuit=breaker,
                max_attempts=2,
            )


class ExternalCallRetryTests(SimpleTestCase):
    def test_retries_then_succeeds(self):
        calls = {'n': 0}

        def flaky():
            calls['n'] += 1
            if calls['n'] < 3:
                raise ExternalRetryableError('transient')
            return 'ok'

        result = external_call(
            service='test',
            operation='flaky',
            fn=flaky,
            max_attempts=4,
        )
        self.assertEqual(result, 'ok')
        self.assertEqual(calls['n'], 3)

    @patch('pinova_backend.security.resilience.logger')
    def test_structured_log_format(self, mock_logger):
        log_external_call(
            service='fedapay',
            operation='POST /transactions',
            latency_ms=42.5,
            attempt=1,
            outcome='success',
            status=200,
        )
        mock_logger.info.assert_called_once()
        payload = json.loads(mock_logger.info.call_args[0][0])
        self.assertEqual(payload['event'], 'external_service')
        self.assertEqual(payload['service'], 'fedapay')
        self.assertEqual(payload['outcome'], 'success')
        self.assertEqual(payload['attempt'], 1)


class FedapayClientResilienceTests(SimpleTestCase):
    @patch('monetization.fedapay_client.requests.request')
    @patch('monetization.fedapay_client.fedapay_headers')
    def test_fedapay_post_retries_on_503(self, mock_headers, mock_request):
        from monetization.fedapay_client import FEDAPAY_CIRCUIT, fedapay_post

        FEDAPAY_CIRCUIT.record_success()
        mock_headers.return_value = {'Authorization': 'Bearer x'}

        fail_resp = MagicMock()
        fail_resp.status_code = 503
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        mock_request.side_effect = [fail_resp, ok_resp]

        resp = fedapay_post('/transactions', json={'amount': 100})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)
