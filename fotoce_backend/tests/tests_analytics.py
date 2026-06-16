"""Tests analytics serveur PostHog."""
from django.test import SimpleTestCase, override_settings


class AnalyticsModuleTests(SimpleTestCase):
    def test_capture_noop_without_api_key(self):
        from fotoce_backend.observability.analytics import capture_event

        self.assertFalse(capture_event(1, 'checkout_success', properties={'flow': 'premium'}))

    @override_settings(POSTHOG_API_KEY='phc_test', POSTHOG_HOST='https://eu.i.posthog.com')
    def test_capture_revenue_recorded_xof(self):
        from unittest.mock import patch

        from fotoce_backend.observability.analytics import capture_revenue_recorded

        with patch('fotoce_backend.observability.analytics.capture_event', return_value=True) as mock_capture:
            ok = capture_revenue_recorded(
                user_id=7,
                flow='premium',
                amount=5000,
                currency='XOF',
                transaction_id='tx_rev',
            )
        self.assertTrue(ok)
        mock_capture.assert_called_once()
        args, kwargs = mock_capture.call_args
        self.assertEqual(args[0], 7)
        self.assertEqual(args[1], 'revenue_recorded')
        props = kwargs['properties']
        self.assertEqual(props['flow'], 'premium')
        self.assertEqual(props['$revenue'], 5000)
        self.assertEqual(props['$currency'], 'XOF')
        self.assertEqual(props['revenue_source'], 'fedapay_webhook')
        self.assertEqual(props['tracking_role'], 'revenue')
        self.assertEqual(props['transaction_id'], 'tx_rev')

    @override_settings(POSTHOG_API_KEY='phc_test', POSTHOG_HOST='https://eu.i.posthog.com')
    def test_capture_revenue_recorded_eur_minor_units(self):
        from unittest.mock import patch

        from fotoce_backend.observability.analytics import capture_revenue_recorded

        with patch('fotoce_backend.observability.analytics.capture_event', return_value=True) as mock_capture:
            capture_revenue_recorded(user_id=1, flow='boost', amount=999, currency='EUR')
        props = mock_capture.call_args.kwargs['properties']
        self.assertEqual(props['$revenue'], 9.99)

    @override_settings(POSTHOG_API_KEY='phc_test', POSTHOG_HOST='https://eu.i.posthog.com')
    def test_capture_checkout_success_emits_revenue_and_checkout(self):
        from unittest.mock import patch

        from fotoce_backend.observability.analytics import capture_checkout_success

        with patch('fotoce_backend.observability.analytics.capture_event', return_value=True) as mock_capture:
            ok = capture_checkout_success(
                user_id=42,
                flow='premium',
                amount=5000,
                transaction_id='tx_1',
            )
        self.assertTrue(ok)
        self.assertEqual(mock_capture.call_count, 2)
        events = [call.args[1] for call in mock_capture.call_args_list]
        self.assertEqual(events, ['revenue_recorded', 'checkout_success'])
        checkout_props = mock_capture.call_args_list[1].kwargs['properties']
        self.assertEqual(checkout_props['flow'], 'premium')
        self.assertEqual(checkout_props['amount'], 5000)
        self.assertEqual(checkout_props['$revenue'], 5000)
        self.assertEqual(checkout_props['revenue_source'], 'fedapay_webhook')

    @override_settings(POSTHOG_API_KEY='phc_test', POSTHOG_HOST='https://eu.i.posthog.com')
    def test_revenue_recorded_never_client_estimate(self):
        from unittest.mock import patch

        from fotoce_backend.observability.analytics import capture_revenue_recorded

        with patch('fotoce_backend.observability.analytics.capture_event', return_value=True) as mock_capture:
            capture_revenue_recorded(user_id=1, flow='premium', amount=1000, currency='XOF')
        props = mock_capture.call_args.kwargs['properties']
        self.assertEqual(props['revenue_source'], 'fedapay_webhook')
        self.assertEqual(props['tracking_role'], 'revenue')
        self.assertNotEqual(props.get('revenue_source'), 'client_estimate')

    @override_settings(POSTHOG_API_KEY='phc_test', POSTHOG_HOST='https://eu.i.posthog.com')
    def test_capture_referral_link_opened(self):
        from unittest.mock import patch

        from fotoce_backend.observability.analytics import capture_referral_link_opened

        with patch('fotoce_backend.observability.analytics.capture_event', return_value=True) as mock_capture:
            capture_referral_link_opened(distinct_id='anon-1', ref_code='ABC', referrer_id=99)
        args, kwargs = mock_capture.call_args
        self.assertEqual(args[1], 'referral_link_opened')
        self.assertEqual(kwargs['properties']['ref_code'], 'ABC')
        self.assertEqual(kwargs['properties']['referrer_id'], 99)

    @override_settings(POSTHOG_API_KEY='phc_test', POSTHOG_HOST='https://eu.i.posthog.com')
    def test_capture_register_with_ref_code(self):
        from unittest.mock import patch

        from fotoce_backend.observability.analytics import capture_register_with_ref_code

        with patch('fotoce_backend.observability.analytics.capture_event', return_value=True) as mock_capture:
            capture_register_with_ref_code(user_id=3, ref_code='XYZ', signup_channel='referral')
        props = mock_capture.call_args.kwargs['properties']
        self.assertTrue(props['has_ref_code'])
        self.assertEqual(props['signup_channel'], 'referral')
