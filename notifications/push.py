import json
import os

from pywebpush import WebPushException, webpush

from .models import PushSubscription


def get_vapid_public_key():
    return os.environ.get('WEB_PUSH_VAPID_PUBLIC_KEY', '').strip()


def is_push_configured():
    return bool(
        os.environ.get('WEB_PUSH_VAPID_PRIVATE_KEY', '').strip()
        and os.environ.get('WEB_PUSH_VAPID_PUBLIC_KEY', '').strip()
        and os.environ.get('WEB_PUSH_VAPID_CLAIMS_SUB', '').strip()
    )


def send_notification_push(notification):
    if not is_push_configured():
        return
    subscriptions = PushSubscription.objects.filter(user=notification.recipient, is_active=True)
    if not subscriptions.exists():
        return
    payload = json.dumps(
        {
            'title': notification.title or 'PINOVA',
            'body': notification.message,
            'notification_type': notification.notification_type,
            'action_url': notification.action_url,
            'notification_id': notification.id,
        }
    )
    vapid_private_key = os.environ.get('WEB_PUSH_VAPID_PRIVATE_KEY', '').strip()
    vapid_claims = {'sub': os.environ.get('WEB_PUSH_VAPID_CLAIMS_SUB', '').strip()}

    for sub in subscriptions:
        subscription_info = {
            'endpoint': sub.endpoint,
            'keys': {
                'p256dh': sub.p256dh,
                'auth': sub.auth,
            },
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims,
            )
        except WebPushException as exc:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status_code in {404, 410}:
                sub.is_active = False
                sub.save(update_fields=['is_active', 'updated_at'])
