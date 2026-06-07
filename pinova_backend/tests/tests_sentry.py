"""Tests Sentry — scrub + middleware."""
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings


class SentryScrubTests(SimpleTestCase):
    def test_scrub_tokens_and_email(self):
        from pinova_backend.observability.sentry import scrub_sentry_event

        event = {
            'request': {
                'headers': {'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.x.y'},
                'data': {'email': 'user@test.invalid', 'refresh': 'secret-refresh'},
            },
            'user': {'email': 'user@test.invalid', 'id': '1'},
        }
        scrubbed = scrub_sentry_event(event)
        self.assertIn('[Filtered]', scrubbed['request']['headers']['Authorization'])
        self.assertEqual(scrubbed['request']['data']['email'], '[Filtered]')
        self.assertEqual(scrubbed['request']['data']['refresh'], '[Filtered]')
        self.assertEqual(scrubbed['user']['email'], '[Filtered]')


@override_settings(SENTRY_DSN='https://example@sentry.io/123')
class SentryApiTimingMiddlewareTests(SimpleTestCase):
    def test_slow_api_triggers_capture(self):
        from pinova_backend.middleware.sentry import SentryApiTimingMiddleware

        factory = RequestFactory()

        def slow_view(request):
            return HttpResponse('ok', status=200)

        middleware = SentryApiTimingMiddleware(lambda req: slow_view(req))

        with patch('pinova_backend.middleware.sentry.capture_slow_api') as mock_capture:
            with patch('pinova_backend.middleware.sentry.time.perf_counter', side_effect=[0, 1.5]):
                response = middleware(factory.get('/api/me/'))
        self.assertEqual(response.status_code, 200)
        mock_capture.assert_called_once()
        self.assertGreaterEqual(mock_capture.call_args.kwargs['duration_ms'], 1000)

    def test_fast_api_skipped(self):
        from pinova_backend.middleware.sentry import SentryApiTimingMiddleware

        factory = RequestFactory()

        middleware = SentryApiTimingMiddleware(lambda req: HttpResponse('ok'))

        with patch('pinova_backend.middleware.sentry.capture_slow_api') as mock_capture:
            with patch('pinova_backend.middleware.sentry.time.perf_counter', side_effect=[0, 0.05]):
                middleware(factory.get('/api/me/'))
        mock_capture.assert_not_called()
