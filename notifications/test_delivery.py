from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from notifications.delivery import (
    DELIVERY_WS_AND_PUSH,
    DELIVERY_WS_FALLBACK_PUSH,
    DELIVERY_WS_ONLY,
    push_group_key,
    resolve_delivery_mode,
    resolve_in_app_toast,
)
from notifications.models import Notification


class NotificationDeliveryPolicyTests(TestCase):
    def setUp(self):
        self.recipient = User.objects.create_user(username='dest', password='x')
        self.sender = User.objects.create_user(username='src', password='x')

    def _notif(self, **kwargs):
        defaults = dict(
            recipient=self.recipient,
            sender=self.sender,
            notification_type='like',
            message='hello',
            metadata={},
        )
        defaults.update(kwargs)
        return Notification(**defaults)

    def test_default_social_is_ws_fallback_push(self):
        n = self._notif(notification_type='like')
        self.assertEqual(resolve_delivery_mode(n), DELIVERY_WS_FALLBACK_PUSH)
        self.assertTrue(resolve_in_app_toast(n))

    def test_payment_is_ws_and_push(self):
        n = self._notif(notification_type='payment')
        self.assertEqual(resolve_delivery_mode(n), DELIVERY_WS_AND_PUSH)

    def test_contest_rank_is_ws_only_and_silent_toast(self):
        n = self._notif(
            notification_type='system',
            metadata={'kind': 'contest_display_rank_change'},
        )
        self.assertEqual(resolve_delivery_mode(n), DELIVERY_WS_ONLY)
        self.assertFalse(resolve_in_app_toast(n))

    def test_push_group_key_pin(self):
        n = self._notif(notification_type='comment', pin_id=99)
        self.assertEqual(push_group_key(n), 'comment:pin:99')

    @patch('notifications.delivery.send_notification_ws', return_value=True)
    @patch('notifications.delivery._deliver_push', return_value=False)
    def test_deliver_skips_push_when_ws_ok_and_fallback_mode(self, *_mocks):
        from notifications.delivery import deliver_notification

        n = Notification.objects.create(
            recipient=self.recipient,
            sender=self.sender,
            notification_type='like',
            message='x',
            metadata={},
        )
        payload = deliver_notification(n)
        self.assertEqual(payload['delivery_mode'], DELIVERY_WS_FALLBACK_PUSH)
        self.assertTrue(payload['ws_sent'])
        self.assertFalse(payload['push_sent'])
