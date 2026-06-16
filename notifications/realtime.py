import json
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from fotoce_backend.security.resilience import log_external_call

logger = logging.getLogger(__name__)


def notifications_group_name(user_id: int) -> str:
    return f'notifications_user_{int(user_id)}'


def notification_ws_payload(notification) -> dict:
    from .delivery import resolve_in_app_toast

    metadata = notification.metadata if isinstance(notification.metadata, dict) else {}
    return {
        'id': notification.id,
        'notification_type': notification.notification_type,
        'title': notification.title or '',
        'message': notification.message,
        'action_url': notification.action_url or '',
        'metadata': metadata,
        'foto_id': notification.foto_id,
        'foto_slug': notification.foto_slug,
        'comment_id': notification.comment_id,
        'is_read': bool(notification.is_read),
        'created_at': notification.created_at.isoformat(),
        'sender_id': notification.sender_id,
        'recipient_id': notification.recipient_id,
        'in_app_toast': resolve_in_app_toast(notification),
    }


def send_notification_ws(notification) -> bool:
    """
    Envoi temps réel WebSocket.
    Retourne True si l'envoi Channels est déclenché, sinon False (dégradation push-only).
    """
    import time

    channel_layer = get_channel_layer()
    if not channel_layer:
        log_external_call(
            service='notification_ws',
            operation='group_send',
            latency_ms=0,
            attempt=1,
            outcome='degraded',
            reason='no_channel_layer',
            notification_id=getattr(notification, 'id', None),
        )
        return False
    start = time.perf_counter()
    try:
        async_to_sync(channel_layer.group_send)(
            notifications_group_name(notification.recipient_id),
            {
                'type': 'notification.event',
                'payload': notification_ws_payload(notification),
            },
        )
        log_external_call(
            service='notification_ws',
            operation='group_send',
            latency_ms=(time.perf_counter() - start) * 1000,
            attempt=1,
            outcome='success',
            notification_id=notification.id,
        )
        return True
    except Exception as exc:
        log_external_call(
            service='notification_ws',
            operation='group_send',
            latency_ms=(time.perf_counter() - start) * 1000,
            attempt=1,
            outcome='degraded',
            reason='send_failed',
            error=str(exc)[:200],
            notification_id=getattr(notification, 'id', None),
        )
        logger.debug('WebSocket notification degraded notification_id=%s', notification.id, exc_info=True)
        return False
