from rest_framework import serializers

from ads import constants as ac
from ads.models import Ad, AdCreative


class AdCreativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdCreative
        fields = (
            'id',
            'headline',
            'body',
            'cta_text',
            'brand_name',
            'brand_logo_url',
            'media_image',
            'media_video_url',
            'aspect_ratio',
            'autoplay_muted_default',
            'duration_seconds_est',
        )


class NativeAdSerializer(serializers.ModelSerializer):
    creative = AdCreativeSerializer(read_only=True)

    class Meta:
        model = Ad
        fields = (
            'id',
            'name',
            'ad_format',
            'destination_url',
            'deep_link',
            'creative',
            'campaign_id',
        )


class PendingEventInSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=ac.PENDING_EVENT_TYPE_CHOICES)
    payload = serializers.DictField()
    dedupe_key = serializers.CharField(required=False, allow_blank=True, max_length=128)


class DeliveryRequestSerializer(serializers.Serializer):
    placement = serializers.ChoiceField(choices=ac.PLACEMENT_CHOICES)
    client = serializers.DictField(required=False, default=dict)
    session_depth = serializers.IntegerField(required=False, min_value=0, default=0)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=6, default=2)


class HideSerializer(serializers.Serializer):
    ad = serializers.PrimaryKeyRelatedField(queryset=Ad.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True, max_length=64)


class ReportSerializer(serializers.Serializer):
    ad = serializers.PrimaryKeyRelatedField(queryset=Ad.objects.all())
    reason = serializers.CharField(max_length=64)
    details = serializers.CharField(required=False, allow_blank=True, default='')
