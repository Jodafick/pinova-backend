from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from contests.contest_notifications import contest_rank_change_metadata
from contests.models import ContestSettings
from notifications.delivery import (
    DELIVERY_WS_AND_PUSH,
    DELIVERY_WS_FALLBACK_PUSH,
    DELIVERY_WS_ONLY,
    enrich_notification_metadata,
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

    def test_contest_milestone_is_ws_and_push(self):
        n = self._notif(
            notification_type='system',
            metadata={'kind': 'contest_milestone_top10'},
        )
        self.assertEqual(resolve_delivery_mode(n), DELIVERY_WS_AND_PUSH)
        self.assertTrue(resolve_in_app_toast(n))

    def test_contest_micro_rank_is_ws_only(self):
        n = self._notif(
            notification_type='system',
            metadata={'kind': 'contest_display_rank_change', 'delivery_mode': DELIVERY_WS_ONLY, 'in_app_toast': False},
        )
        self.assertEqual(resolve_delivery_mode(n), DELIVERY_WS_ONLY)
        self.assertFalse(resolve_in_app_toast(n))

    def test_payment_is_ws_and_push(self):
        n = self._notif(notification_type='payment')
        self.assertEqual(resolve_delivery_mode(n), DELIVERY_WS_AND_PUSH)

    def test_enrich_metadata_contest_new_month(self):
        md = enrich_notification_metadata({'kind': 'contest_new_month'}, notification_type='system')
        self.assertEqual(md['delivery_mode'], DELIVERY_WS_AND_PUSH)
        self.assertTrue(md['in_app_toast'])

    def test_push_group_key_pin(self):
        n = self._notif(notification_type='comment', foto_id=99)
        self.assertEqual(push_group_key(n), 'comment:pin:99')

    def test_contest_rank_change_milestone_top10(self):
        settings = ContestSettings(contest_key='2026-03', notify_top_10=True)
        md = contest_rank_change_metadata(settings, prev_rank=15, new_rank=8)
        self.assertEqual(md['kind'], 'contest_milestone_top10')
        self.assertEqual(md['delivery_mode'], DELIVERY_WS_AND_PUSH)

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
