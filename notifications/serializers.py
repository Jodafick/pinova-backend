from rest_framework import serializers
from .models import Notification, PushSubscription

class NotificationSerializer(serializers.ModelSerializer):
    sender_username = serializers.SerializerMethodField()
    sender_avatar_color = serializers.SerializerMethodField()
    sender_avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
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
            'sender_username',
            'sender_avatar_color',
            'sender_avatar_url',
        ]

    def get_sender_username(self, obj):
        return obj.sender.username if obj.sender else "PINOVA"

    def get_sender_avatar_color(self, obj):
        if obj.sender_id and getattr(obj.sender, 'profile', None):
            return obj.sender.profile.avatar_color or 'bg-neutral-400'
        return 'bg-neutral-400'

    def get_sender_avatar_url(self, obj):
        request = self.context.get('request')
        avatar = getattr(getattr(obj.sender, 'profile', None), 'avatar', None)
        if not obj.sender_id or not avatar or not getattr(avatar, 'name', None):
            return None
        url = avatar.url
        return request.build_absolute_uri(url) if request else url


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ['endpoint', 'p256dh', 'auth']
