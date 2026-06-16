import json

from rest_framework import serializers

from fotos.upload_security import (
    validate_image_magic_bytes,
    validate_image_size,
    validate_video_magic_bytes,
)

from .boost_catalog import PACKAGE_KIND_CAMPAIGN, active_packages_for_kind
from .models import BoostPackage, PartnerCampaign, FotoBoost, FotoPromoCampaign
from .targeting import normalize_targeting


class PartnerCampaignSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PartnerCampaign
        fields = [
            'id',
            'title',
            'body',
            'sponsor_name',
            'image',
            'image_url',
            'cta_label',
            'cta_url',
            'topic_slug',
            'country_code',
            'priority',
            'is_active',
            'starts_at',
            'ends_at',
            'impressions',
            'clicks',
            'created_at',
        ]
        read_only_fields = ['impressions', 'clicks', 'created_at', 'image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if not obj.image or not request:
            return ''
        return request.build_absolute_uri(obj.image.url)


class PartnerCampaignWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerCampaign
        fields = [
            'title',
            'body',
            'sponsor_name',
            'image',
            'cta_label',
            'cta_url',
            'topic_slug',
            'country_code',
            'priority',
            'is_active',
            'starts_at',
            'ends_at',
        ]


class BoostPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoostPackage
        fields = ['slug', 'label', 'package_kind', 'duration_hours', 'amount', 'currency_iso']


class FotoBoostHistorySerializer(serializers.ModelSerializer):
    foto_slug = serializers.CharField(source='foto.slug', read_only=True)
    pin_title = serializers.CharField(source='foto.title', read_only=True)
    package_label = serializers.CharField(source='package.label', read_only=True)
    package_slug = serializers.CharField(source='package.slug', read_only=True)

    class Meta:
        model = FotoBoost
        fields = [
            'id',
            'foto_slug',
            'pin_title',
            'package_slug',
            'package_label',
            'status',
            'starts_at',
            'ends_at',
            'created_at',
        ]


class FotoPromoCampaignSerializer(serializers.ModelSerializer):
    foto_slug = serializers.SerializerMethodField()
    pin_title = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()
    package_label = serializers.CharField(source='package.label', read_only=True)
    package_slug = serializers.CharField(source='package.slug', read_only=True)
    ctr = serializers.SerializerMethodField()

    class Meta:
        model = FotoPromoCampaign
        fields = [
            'id',
            'foto_slug',
            'pin_title',
            'image_url',
            'media_url',
            'media_type',
            'headline',
            'body',
            'cta_label',
            'cta_url',
            'topic_slug',
            'targeting',
            'package_slug',
            'package_label',
            'status',
            'starts_at',
            'ends_at',
            'impressions',
            'clicks',
            'pin_views',
            'ctr',
            'created_at',
        ]

    def get_foto_slug(self, obj):
        return obj.foto.slug if obj.foto_id else ''

    def get_foto_title(self, obj):
        return obj.foto.title if obj.foto_id else ''

    def _media_abs(self, obj):
        request = self.context.get('request')
        if not request:
            return '', obj.media_type or FotoPromoCampaign.MEDIA_IMAGE
        if obj.media:
            return request.build_absolute_uri(obj.media.url), obj.media_type or FotoPromoCampaign.MEDIA_IMAGE
        if obj.image:
            return request.build_absolute_uri(obj.image.url), FotoPromoCampaign.MEDIA_IMAGE
        if obj.foto_id and obj.foto.image:
            return request.build_absolute_uri(obj.foto.image.url), FotoPromoCampaign.MEDIA_IMAGE
        return '', FotoPromoCampaign.MEDIA_IMAGE

    def get_image_url(self, obj):
        url, _ = self._media_abs(obj)
        return url

    def get_media_url(self, obj):
        url, _ = self._media_abs(obj)
        return url

    def get_ctr(self, obj):
        if obj.impressions <= 0:
            return 0.0
        return round((obj.clicks / obj.impressions) * 100, 2)


class TargetingField(serializers.JSONField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            raw = data.strip()
            if not raw:
                return {}
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError('JSON de ciblage invalide.') from exc
        parsed = super().to_internal_value(data)
        return normalize_targeting(parsed if isinstance(parsed, dict) else {})


class FotoPromoCampaignWriteSerializer(serializers.ModelSerializer):
    package = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=active_packages_for_kind(PACKAGE_KIND_CAMPAIGN),
    )
    targeting = TargetingField(required=False)

    class Meta:
        model = FotoPromoCampaign
        fields = [
            'package',
            'headline',
            'body',
            'topic_slug',
            'image',
            'media',
            'media_type',
            'targeting',
            'cta_label',
            'cta_url',
        ]

    def validate_media_type(self, value):
        v = (value or FotoPromoCampaign.MEDIA_IMAGE).lower()
        if v not in (FotoPromoCampaign.MEDIA_IMAGE, FotoPromoCampaign.MEDIA_VIDEO):
            raise serializers.ValidationError('Type média invalide.')
        return v

    def validate_image(self, value):
        if not value:
            return value
        request = self.context.get('request')
        validate_image_size(value, request=request)
        validate_image_magic_bytes(value, request=request)
        return value

    def validate_media(self, value):
        if not value:
            return value
        request = self.context.get('request')
        raw_type = self.initial_data.get('media_type')
        media_type = (raw_type if isinstance(raw_type, str) else '').strip().lower()
        if not media_type:
            name = (getattr(value, 'name', '') or '').lower()
            media_type = (
                FotoPromoCampaign.MEDIA_VIDEO
                if name.endswith(('.mp4', '.webm', '.mov', '.m4v'))
                else FotoPromoCampaign.MEDIA_IMAGE
            )
        if media_type == FotoPromoCampaign.MEDIA_VIDEO:
            validate_video_magic_bytes(value, request=request)
        else:
            validate_image_size(value, request=request)
            validate_image_magic_bytes(value, request=request)
        return value

    def validate(self, attrs):
        headline = (attrs.get('headline') or '').strip()
        cta_url = (attrs.get('cta_url') or '').strip()
        if not headline:
            raise serializers.ValidationError({'headline': 'Titre requis.'})
        if not cta_url:
            raise serializers.ValidationError({'cta_url': 'Lien de destination requis.'})
        attrs['headline'] = headline
        attrs['cta_url'] = cta_url
        if not (attrs.get('cta_label') or '').strip():
            attrs['cta_label'] = 'En savoir plus'
        targeting = normalize_targeting(attrs.get('targeting') or {})
        topic_slug = (attrs.get('topic_slug') or '').strip()
        if topic_slug and not targeting.get('topics'):
            targeting['topics'] = [topic_slug.lower()]
        attrs['targeting'] = targeting
        if attrs.get('media') and attrs.get('media_type') == FotoPromoCampaign.MEDIA_VIDEO:
            attrs.pop('image', None)
        if attrs.get('media') and not attrs.get('media_type'):
            name = (attrs['media'].name or '').lower()
            if name.endswith(('.mp4', '.webm', '.mov', '.m4v')):
                attrs['media_type'] = FotoPromoCampaign.MEDIA_VIDEO
            else:
                attrs['media_type'] = FotoPromoCampaign.MEDIA_IMAGE
        return attrs

    def create(self, validated_data):
        return FotoPromoCampaign.objects.create(
            owner=self.context['request'].user,
            foto=None,
            **validated_data,
        )
