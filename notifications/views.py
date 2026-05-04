from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from accounts.blocking import blocked_mutual_user_ids

from pinova_backend.unread_notifications_middleware import invalidate_unread_notifications_header_cache

from .models import Notification, PushSubscription
from .serializers import NotificationSerializer, PushSubscriptionSerializer
from .push import get_vapid_public_key, is_push_configured
from .pagination import NotificationPagination


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
        serializer = PushSubscriptionSerializer(data=request.data)
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
    def push_unsubscribe(self, request):
        endpoint = str(request.data.get('endpoint') or '').strip()
        if not endpoint:
            return Response({'error': 'endpoint is required'}, status=status.HTTP_400_BAD_REQUEST)
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).update(is_active=False)
        return Response({'status': 'unsubscribed'})
