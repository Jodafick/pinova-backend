from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from accounts.blocking import blocked_mutual_user_ids

from pinova_backend.middleware.unread_notifications import invalidate_unread_notifications_header_cache

from .models import ExpoPushToken, Notification, PushSubscription
from .serializers import (
    ExpoPushRegisterSerializer,
    NotificationSerializer,
    PushDeviceStatusSerializer,
    PushSubscribeSerializer,
    PushSubscriptionSerializer,
)
from .push import get_vapid_public_key, is_push_configured
from .pagination import NotificationPagination
from .realtime import notification_ws_payload


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = (
            Notification.objects.filter(recipient=self.request.user)
            .select_related('sender', 'sender__profile')
            .only(
                'id',
                'notification_type',
                'title',
                'message',
                'action_url',
                'metadata',
                'pin_id',
                'pin_slug',
                'comment_id',
                'is_read',
                'created_at',
                'sender_id',
                'recipient_id',
            )
        )
        forb = blocked_mutual_user_ids(self.request.user)
        if forb:
            qs = qs.filter(Q(sender__isnull=True) | ~Q(sender_id__in=forb))
        return qs

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        self.get_queryset().update(is_read=True)
        invalidate_unread_notifications_header_cache(request.user.pk)
        return Response({'status': 'all notifications marked as read'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'count': count})

    @action(detail=False, methods=['get'], url_path='events')
    def events(self, request):
        """
        Polling HTTP complémentaire au WebSocket `/api/notifications/ws`.
        Aligné sur `contest/leaderboard/events` : deltas depuis `since_id`.
        """
        since_id = int(request.query_params.get('since_id', 0) or 0)
        limit = min(max(int(request.query_params.get('limit', 100) or 100), 1), 300)
        qs = self.get_queryset().order_by('id')
        if since_id > 0:
            qs = qs.filter(id__gt=since_id)
        rows = list(qs[:limit])
        return Response(
            {
                'results': [notification_ws_payload(row) for row in rows],
                'last_id': rows[-1].id if rows else since_id,
            }
        )

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({'status': 'notification marked as read'})

    @action(detail=True, methods=['post'])
    def mark_as_unread(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = False
        notification.save(update_fields=['is_read'])
        return Response({'status': 'notification marked as unread'})

    @action(detail=False, methods=['get'])
    def push_public_key(self, request):
        return Response({
            'enabled': is_push_configured(),
            'public_key': get_vapid_public_key(),
        })

    @action(detail=False, methods=['post'])
    def push_subscribe(self, request):
        serializer = PushSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        sub, _ = PushSubscription.objects.update_or_create(
            endpoint=payload['endpoint'],
            defaults={
                'user': request.user,
                'p256dh': payload['p256dh'],
                'auth': payload['auth'],
                'is_active': True,
                'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:255],
            },
        )
        return Response({'status': 'subscribed', 'id': sub.id}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def push_device_status(self, request):
        """
        Source de vérité pour l’UI : cet endpoint est-il enregistré et actif pour l’utilisateur connecté ?
        Un même compte peut avoir plusieurs appareils (plusieurs lignes PushSubscription).
        """
        serializer = PushDeviceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = (serializer.validated_data.get('endpoint') or '').strip()
        if not endpoint:
            return Response(
                {
                    'backend_registered': False,
                    'backend_active': False,
                },
            )
        row = PushSubscription.objects.filter(endpoint=endpoint).only('user_id', 'is_active').first()
        if row is None or row.user_id != request.user.pk:
            return Response(
                {
                    'backend_registered': False,
                    'backend_active': False,
                },
            )
        return Response(
            {
                'backend_registered': True,
                'backend_active': bool(row.is_active),
            },
        )

    @action(detail=False, methods=['post'])
    def push_unsubscribe(self, request):
        endpoint = str(request.data.get('endpoint') or '').strip()
        if not endpoint:
            return Response({'error': 'endpoint is required'}, status=status.HTTP_400_BAD_REQUEST)
        # Un seul compte doit pouvoir désactiver sa ligne pour cet endpoint (plusieurs appareils =
        # plusieurs endpoints ; un endpoint = un enregistrement par user_id après subscribe).
        PushSubscription.objects.filter(endpoint=endpoint, user=request.user).update(is_active=False)
        return Response({'status': 'unsubscribed'})

    @action(detail=False, methods=['post'])
    def expo_push_register(self, request):
        serializer = ExpoPushRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        token = payload['token']
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        plat = (payload.get('platform') or '')[:24]
        row, _ = ExpoPushToken.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'platform': plat,
                'is_active': True,
                'user_agent': ua,
            },
        )
        return Response({'status': 'registered', 'id': row.id}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def expo_push_unregister(self, request):
        token = str(request.data.get('token') or '').strip()
        if not token:
            return Response({'error': 'token is required'}, status=status.HTTP_400_BAD_REQUEST)
        # Le jeton est propre à l’appareil / installation : on désactive sans filtrer sur user
        # (déconnexion propre au même device après changement de compte sur le serveur).
        ExpoPushToken.objects.filter(token=token).update(is_active=False)
        return Response({'status': 'unregistered'})
