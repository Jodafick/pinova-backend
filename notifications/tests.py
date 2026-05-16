from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import PushSubscription


class PushDeviceStatusTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user('alice', 'a@test.invalid', 'pwd')
        self.u2 = User.objects.create_user('bob', 'b@test.invalid', 'pwd')
        self.client = APIClient()

    def test_status_active_only_for_owner(self):
        PushSubscription.objects.create(
            user=self.u1,
            endpoint='https://fcm.test/p1',
            p256dh='k' * 10,
            auth='a' * 10,
            is_active=True,
        )
        self.client.force_authenticate(user=self.u1)
        r = self.client.post(
            '/api/notifications/push_device_status/',
            {'endpoint': 'https://fcm.test/p1'},
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['backend_registered'])
        self.assertTrue(r.data['backend_active'])

        self.client.force_authenticate(user=self.u2)
        r2 = self.client.post(
            '/api/notifications/push_device_status/',
            {'endpoint': 'https://fcm.test/p1'},
            format='json',
        )
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.data['backend_registered'])
        self.assertFalse(r2.data['backend_active'])

    def test_status_inactive_row(self):
        PushSubscription.objects.create(
            user=self.u1,
            endpoint='https://fcm.test/off',
            p256dh='k' * 10,
            auth='a' * 10,
            is_active=False,
        )
        self.client.force_authenticate(user=self.u1)
        r = self.client.post(
            '/api/notifications/push_device_status/',
            {'endpoint': 'https://fcm.test/off'},
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['backend_registered'])
        self.assertFalse(r.data['backend_active'])

    def test_unsubscribe_scoped_to_current_user(self):
        PushSubscription.objects.create(
            user=self.u1,
            endpoint='https://fcm.test/x',
            p256dh='k' * 10,
            auth='a' * 10,
            is_active=True,
        )
        self.client.force_authenticate(user=self.u2)
        self.client.post(
            '/api/notifications/push_unsubscribe/',
            {'endpoint': 'https://fcm.test/x'},
            format='json',
        )
        row = PushSubscription.objects.get(endpoint='https://fcm.test/x')
        self.assertTrue(row.is_active)

        self.client.force_authenticate(user=self.u1)
        self.client.post(
            '/api/notifications/push_unsubscribe/',
            {'endpoint': 'https://fcm.test/x'},
            format='json',
        )
        row.refresh_from_db()
        self.assertFalse(row.is_active)
