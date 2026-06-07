"""Tests sécurité webhook FedaPay (secret, idempotence, montant)."""

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile, SubscriptionPayment
from monetization.fedapay_webhook import get_fedapay_webhook_secret
from monetization.models import WebhookEventProcessed

WEBHOOK_URL = '/api/subscription/webhook/fedapay/'
SECRET = 'test-webhook-secret'


@override_settings(DEBUG=True, FEDAPAY_WEBHOOK_SECRET=SECRET)
class FedapayWebhookSecretTests(APITestCase):
    def test_missing_secret_in_production_raises(self):
        with override_settings(DEBUG=False, FEDAPAY_WEBHOOK_SECRET=''):
            with self.assertRaises(ImproperlyConfigured):
                get_fedapay_webhook_secret()

    def test_invalid_secret_rejected(self):
        user = User.objects.create_user('subuser', 'sub@example.com', 'Pinova2026!')
        SubscriptionPayment.objects.create(
            user=user,
            plan=Profile.PLAN_PLUS,
            billing_cycle=SubscriptionPayment.BILLING_MONTHLY,
            amount=5000,
            fedapay_transaction_id='tx-secret-1',
        )
        response = self.client.post(
            WEBHOOK_URL,
            {'id': 'tx-secret-1', 'status': 'approved', 'amount': 5000},
            format='json',
            HTTP_X_WEBHOOK_TOKEN='wrong-secret',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get('error'), 'Invalid webhook token')

    def test_missing_token_when_secret_configured(self):
        response = self.client.post(
            WEBHOOK_URL,
            {'id': 'tx-no-token', 'status': 'approved'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(DEBUG=True, FEDAPAY_WEBHOOK_SECRET=SECRET)
class FedapayWebhookProcessingTests(APITestCase):
    def _create_payment(self, tx_id: str, amount: int = 5000) -> SubscriptionPayment:
        user = User.objects.create_user(
            f'user_{tx_id}',
            f'{tx_id}@example.com',
            'Pinova2026!',
        )
        return SubscriptionPayment.objects.create(
            user=user,
            plan=Profile.PLAN_PLUS,
            billing_cycle=SubscriptionPayment.BILLING_MONTHLY,
            amount=amount,
            fedapay_transaction_id=tx_id,
        )

    def _post_webhook(self, tx_id: str, *, amount: int = 5000, status_value: str = 'approved'):
        return self.client.post(
            WEBHOOK_URL,
            {'id': tx_id, 'status': status_value, 'amount': amount},
            format='json',
            HTTP_X_WEBHOOK_TOKEN=SECRET,
        )

    def test_replay_skips_activation(self):
        payment = self._create_payment('tx-sub-1')
        first = self._post_webhook('tx-sub-1', amount=payment.amount)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data.get('status'), 'approved')
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.STATUS_APPROVED)
        self.assertEqual(WebhookEventProcessed.objects.filter(transaction_id='tx-sub-1').count(), 1)

        replay = self._post_webhook('tx-sub-1', amount=payment.amount)
        self.assertEqual(replay.status_code, status.HTTP_200_OK)
        self.assertTrue(replay.data.get('skipped'))
        self.assertEqual(replay.data.get('status'), 'already_processed')
        self.assertEqual(WebhookEventProcessed.objects.filter(transaction_id='tx-sub-1').count(), 1)

    def test_amount_mismatch_skips_activation(self):
        payment = self._create_payment('tx-mismatch', amount=5000)
        response = self._post_webhook('tx-mismatch', amount=1000)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('status'), 'amount_mismatch')
        self.assertTrue(response.data.get('skipped'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.STATUS_PENDING)
        self.assertFalse(WebhookEventProcessed.objects.filter(transaction_id='tx-mismatch').exists())
