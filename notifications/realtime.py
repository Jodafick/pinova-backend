import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def notifications_group_name(user_id: int) -> str:
    return f'notifications_user_{int(user_id)}'


def notification_ws_payload(notification) -> dict:
    metadata = notification.metadata if isinstance(notification.metadata, dict) else {}
    return {
        'id': notification.id,
        'notification_type': notification.notification_type,
        'title': notification.title or '',
        'message': notification.message,
        'action_url': notification.action_url or '',
        'metadata': metadata,
        'pin_id': notification.pin_id,
        'pin_slug': notification.pin_slug,
        'comment_id': notification.comment_id,
        'is_read': bool(notification.is_read),
        'created_at': notification.created_at.isoformat(),
        'sender_id': notification.sender_id,
        'recipient_id': notification.recipient_id,
    }


def send_notification_ws(notification) -> bool:
    """
    Envoi temps réel WebSocket.
    Retourne True si l'envoi Channels est déclenché, sinon False (fallback).
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return False
    try:
        async_to_sync(channel_layer.group_send)(
            notifications_group_name(notification.recipient_id),
            {
                'type': 'notification.event',
                'payload': notification_ws_payload(notification),
            },
        )
        return True
    except Exception:
        logger.exception('WebSocket notification send failed for notification_id=%s', notification.id)
        return False
