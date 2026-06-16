"""Tests unitaires de la politique mot de passe Fotoce."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.password_policy import (
    PASSWORD_VALID_EXAMPLE,
    FotocePasswordValidator,
    evaluate_fotoce_password,
    get_password_rules_payload,
    validate_fotoce_password,
)


class FotocePasswordPolicyUnitTests(SimpleTestCase):
    def test_valid_password_passes(self):
        self.assertEqual(evaluate_fotoce_password('Fotoce2026'), [])
        validate_fotoce_password('Fotoce2026')

    def test_too_short_fails(self):
        failed = evaluate_fotoce_password('Ab1')
        self.assertIn('min_length', failed)

    def test_missing_letter_fails(self):
        failed = evaluate_fotoce_password('12345678')
        self.assertIn('has_letter', failed)

    def test_missing_digit_fails(self):
        failed = evaluate_fotoce_password('Password')
        self.assertIn('has_digit', failed)

    def test_trivial_list_fails(self):
        failed = evaluate_fotoce_password('password123')
        self.assertIn('not_trivial', failed)

    def test_email_local_part_fails(self):
        failed = evaluate_fotoce_password('jean1234', email='jean@example.com')
        self.assertIn('not_trivial', failed)

    def test_username_fails(self):
        failed = evaluate_fotoce_password('creator99', username='creator')
        self.assertIn('not_trivial', failed)

    def test_validator_raises_one_message_per_rule(self):
        validator = FotocePasswordValidator()
        with self.assertRaises(ValidationError) as ctx:
            validator.validate('abc')
        codes = [err.code for err in ctx.exception.error_list]
        self.assertIn('min_length', codes)
        self.assertIn('has_digit', codes)

    def test_rules_payload_fr_and_en(self):
        fr = get_password_rules_payload('fr')
        en = get_password_rules_payload('en')
        self.assertEqual(fr['valid_example'], PASSWORD_VALID_EXAMPLE)
        self.assertEqual(len(fr['rules']), 4)
        self.assertNotEqual(fr['rules'][0]['message'], en['rules'][0]['message'])


class PasswordRulesApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_password_rules_default_fr(self):
        r = self.client.get('/api/auth/password-rules/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['min_length'], 8)
        self.assertEqual(len(r.data['rules']), 4)

    def test_get_password_rules_en_header(self):
        r = self.client.get('/api/auth/password-rules/', HTTP_X_FOTOCE_LANG='en')
        self.assertEqual(r.status_code, 200)
        self.assertIn('At least', r.data['rules'][0]['message'])


class RegisterPasswordPolicyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_rejects_weak_password(self):
        r = self.client.post(
            '/api/auth/registration/',
            {
                'email': 'newuser@example.com',
                'username': 'newuser',
                'password1': 'password123',
                'password2': 'password123',
            },
            format='json',
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('password1', r.data)

    def test_register_accepts_strong_password(self):
        r = self.client.post(
            '/api/auth/registration/',
            {
                'email': 'strong@example.com',
                'username': 'stronguser',
                'password1': PASSWORD_VALID_EXAMPLE,
                'password2': PASSWORD_VALID_EXAMPLE,
            },
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(User.objects.filter(email='strong@example.com').exists())
