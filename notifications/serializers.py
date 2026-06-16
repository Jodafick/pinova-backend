from rest_framework import serializers

from fotos.topic_i18n import SUPPORTED_TOPIC_LANGS

from fotoce_backend.media_serving.cache import build_versioned_media_url

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
            'foto_id',
            'foto_slug',
            'comment_id',
            'is_read',
            'created_at',
            'sender_username',
            'sender_avatar_color',
            'sender_avatar_url',
        ]

    def get_sender_username(self, obj):
        return obj.sender.username if obj.sender else "FOTOCE"

    def get_sender_avatar_color(self, obj):
        if obj.sender_id and getattr(obj.sender, 'profile', None):
            return obj.sender.profile.avatar_color or 'bg-neutral-400'
        return 'bg-neutral-400'

    def get_sender_avatar_url(self, obj):
        request = self.context.get('request')
        avatar = getattr(getattr(obj.sender, 'profile', None), 'avatar', None)
        if not obj.sender_id or not avatar or not getattr(avatar, 'name', None):
            return None
        if request:
            return build_versioned_media_url(request, avatar)
        return avatar.url

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not request:
            return data
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return data

        from .notification_i18n import localize_notification_strings, recipient_language

        md = instance.metadata if isinstance(instance.metadata, dict) else {}
        canon = md.get('i18n')
        if not isinstance(canon, dict):
            return data
        msg_fr = canon.get('message_fr')
        if not msg_fr:
            return data

        qp = (request.query_params.get('lang') or '').strip().lower().split('-')[0]
        if qp in SUPPORTED_TOPIC_LANGS:
            lang1 = qp
        else:
            lang1 = recipient_language(user)

        lang0_raw = canon.get('display_lang')
        lang0 = (
            lang0_raw.strip().lower().split('-')[0]
            if isinstance(lang0_raw, str) and lang0_raw.strip()
            else None
        )
        if lang0 == lang1:
            return data

        tit_fr = str(canon.get('title_fr') or '')
        tit, msg = localize_notification_strings(tit_fr, str(msg_fr), lang1)
        data['title'] = tit or data.get('title') or ''
        data['message'] = msg or data.get('message') or ''
        return data


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ['endpoint', 'p256dh', 'auth']


class PushSubscribeSerializer(serializers.Serializer):
    """Inscription push — sans validation d'unicité (update_or_create côté vue)."""

    endpoint = serializers.CharField(max_length=500, trim_whitespace=True)
    p256dh = serializers.CharField(max_length=255, trim_whitespace=True)
    auth = serializers.CharField(max_length=255, trim_whitespace=True)


class ExpoPushRegisterSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=400, trim_whitespace=True)
    platform = serializers.CharField(max_length=24, required=False, allow_blank=True, default='')

    def validate_token(self, value):
        s = value.strip()
        # Longueur max : alignée sur le CharField (400). L’ancienne borne 390 rejetait à tort des jetons valides.
        if len(s) < 24:
            raise serializers.ValidationError('Invalid push token length.')
        if not s.startswith('ExponentPushToken['):
            raise serializers.ValidationError('Invalid Expo push token format.')
        return s


class PushDeviceStatusSerializer(serializers.Serializer):
    """État serveur de l’endpoint web push pour cet appareil / navigateur."""

    endpoint = serializers.CharField(required=False, allow_blank=True, max_length=500, trim_whitespace=True)
