"""Tests headers sécurité et audit permissions."""

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from io import StringIO


class SecurityHeadersSettingsTests(SimpleTestCase):
    @override_settings(
        DEBUG=False,
        SECURE_CONTENT_TYPE_NOSNIFF=True,
        X_FRAME_OPTIONS='DENY',
        SECURE_HSTS_SECONDS=60 * 60 * 24 * 365,
        CONTENT_SECURITY_POLICY="default-src 'self'; script-src 'self'; img-src 'self' data: https:",
    )
    def test_production_security_settings_present(self):
        from django.conf import settings

        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 60 * 60 * 24 * 365)
        self.assertIn("script-src 'self'", settings.CONTENT_SECURITY_POLICY)


class DeployChecksTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_deploy_check_fails_when_debug_true(self):
        from fotoce_backend.core.checks import check_debug_disabled_for_production

        errors = check_debug_disabled_for_production(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, 'fotoce.E001')

    @override_settings(DEBUG=False)
    def test_deploy_check_passes_when_debug_false(self):
        from fotoce_backend.core.checks import check_debug_disabled_for_production

        self.assertEqual(check_debug_disabled_for_production(None), [])


class AuditPublicApiPermissionsCommandTests(SimpleTestCase):
    def test_audit_command_runs(self):
        out = StringIO()
        call_command('audit_public_api_permissions', '--all-public', stdout=out)
        self.assertIn('AllowAny', out.getvalue())

    def test_audit_fail_on_findings_passes(self):
        out = StringIO()
        err = StringIO()
        call_command(
            'audit_public_api_permissions',
            '--fail-on-findings',
            stdout=out,
            stderr=err,
        )
        self.assertIn('Aucun endpoint concerné', out.getvalue() + err.getvalue())


class ProductionDeployChecksTests(SimpleTestCase):
    @override_settings(DEBUG=False, FEDAPAY_WEBHOOK_SECRET='prod-webhook-secret')
    def test_fedapay_secret_check_passes_when_set(self):
        from fotoce_backend.core.checks import check_fedapay_webhook_secret_in_production

        self.assertEqual(check_fedapay_webhook_secret_in_production(None), [])

    @override_settings(DEBUG=False, FEDAPAY_WEBHOOK_SECRET='')
    def test_fedapay_secret_check_fails_when_missing(self):
        from fotoce_backend.core.checks import check_fedapay_webhook_secret_in_production

        errors = check_fedapay_webhook_secret_in_production(None)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, 'fotoce.E007')
