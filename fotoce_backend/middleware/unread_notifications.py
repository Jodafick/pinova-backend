"""Ajoute X-Fotoce-Unread-Notifications sur les réponses API (JWT Bearer) sans requête dédiée côté client."""

from django.core.cache import cache
from django.db.models import Q
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication

from notifications.models import Notification

UNREAD_NOTIFICATION_HEADER = 'X-Fotoce-Unread-Notifications'
LEGACY_UNREAD_NOTIFICATION_HEADER = 'X-Pinova-Unread-Notifications'
UNREAD_HDR_CACHE_PREFIX = 'fotoce:unread_ns_hdr:'
UNREAD_HDR_CACHE_SECONDS = 12


def unread_header_cache_key(user_id: int) -> str:
    return f'{UNREAD_HDR_CACHE_PREFIX}{user_id}'


def invalidate_unread_notifications_header_cache(user_id: int) -> None:
    cache.delete(unread_header_cache_key(user_id))


def _skipped_path(path: str) -> bool:
    if not path.startswith('/api/'):
        return True
    if path.startswith('/admin/'):
        return True
    return False


def _unread_count(user):
    """Même filtres blocage que la liste notifications (NotificationViewSet.get_queryset)."""
    from accounts.blocking import blocked_mutual_user_ids

    qs = Notification.objects.filter(recipient=user, is_read=False).only('id')
    forb = blocked_mutual_user_ids(user)
    if forb:
        qs = qs.filter(Q(sender__isnull=True) | ~Q(sender_id__in=forb))
    return qs.count()


class UnreadNotificationsHeaderMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if _skipped_path(request.path or ''):
            return response

        jwt_auth = JWTAuthentication()
        try:
            auth_result = jwt_auth.authenticate(request)
        except Exception:
            auth_result = None

        if not auth_result:
            return response

        user = auth_result[0]
        ck = unread_header_cache_key(user.pk)
        n = cache.get(ck)
        if n is None:
            n = _unread_count(user)
            cache.set(ck, n, UNREAD_HDR_CACHE_SECONDS)

        response[UNREAD_NOTIFICATION_HEADER] = str(int(n))
        response[LEGACY_UNREAD_NOTIFICATION_HEADER] = str(int(n))
        return response
