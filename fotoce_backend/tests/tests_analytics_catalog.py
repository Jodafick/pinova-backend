"""Catalogue événements business PostHog — cohérence validation live."""
import sys
from pathlib import Path

from django.test import SimpleTestCase

_SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(_SCRIPTS))
from verify_posthog_business_events import REQUIRED_EVENTS  # noqa: E402


class BusinessEventCatalogTests(SimpleTestCase):
    def test_required_events_count_and_prefixes(self):
        names = set(REQUIRED_EVENTS)
        self.assertIn('landing_viewed', names)
        self.assertIn('register_started', names)
        self.assertIn('register_completed', names)
        self.assertIn('onboarding_completed', names)
        self.assertIn('first_foto_published', names)
        self.assertIn('premium_viewed', names)
        self.assertIn('checkout_started', names)
        self.assertIn('revenue_recorded', names)
        self.assertIn('referral_link_opened', names)
        self.assertTrue(any(e.startswith('retention_cohort_') for e in names))
        self.assertEqual(len(names), 19)

    def test_backend_analytics_exports_revenue_and_referral(self):
        from fotoce_backend.observability import analytics as mod

        for fn_name in (
            'capture_revenue_recorded',
            'capture_checkout_success',
            'capture_referral_link_opened',
            'capture_register_with_ref_code',
        ):
            self.assertTrue(hasattr(mod, fn_name), fn_name)
