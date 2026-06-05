from rest_framework import serializers

from .models import BoostPackage, PartnerCampaign, PinBoost, PinPromoCampaign


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
        fields = ['slug', 'label', 'duration_hours', 'amount', 'currency_iso']


class PinBoostHistorySerializer(serializers.ModelSerializer):
    pin_slug = serializers.CharField(source='pin.slug', read_only=True)
    pin_title = serializers.CharField(source='pin.title', read_only=True)
    package_label = serializers.CharField(source='package.label', read_only=True)
    package_slug = serializers.CharField(source='package.slug', read_only=True)

    class Meta:
        model = PinBoost
        fields = [
            'id',
            'pin_slug',
            'pin_title',
            'package_slug',
            'package_label',
            'status',
            'starts_at',
            'ends_at',
            'created_at',
        ]


class PinPromoCampaignSerializer(serializers.ModelSerializer):
    pin_slug = serializers.SerializerMethodField()
    pin_title = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    package_label = serializers.CharField(source='package.label', read_only=True)
    package_slug = serializers.CharField(source='package.slug', read_only=True)
    ctr = serializers.SerializerMethodField()

    class Meta:
        model = PinPromoCampaign
        fields = [
            'id',
            'pin_slug',
            'pin_title',
            'image_url',
            'headline',
            'body',
            'cta_label',
            'cta_url',
            'topic_slug',
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

    def get_pin_slug(self, obj):
        return obj.pin.slug if obj.pin_id else ''

    def get_pin_title(self, obj):
        return obj.pin.title if obj.pin_id else ''

    def get_image_url(self, obj):
        request = self.context.get('request')
        if not request:
            return ''
        if obj.image:
            return request.build_absolute_uri(obj.image.url)
        if obj.pin_id and obj.pin.image:
            return request.build_absolute_uri(obj.pin.image.url)
        return ''

    def get_ctr(self, obj):
        if obj.impressions <= 0:
            return 0.0
        return round((obj.clicks / obj.impressions) * 100, 2)


class PinPromoCampaignWriteSerializer(serializers.ModelSerializer):
    package = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=BoostPackage.objects.filter(is_active=True),
    )

    class Meta:
        model = PinPromoCampaign
        fields = [
            'package',
            'headline',
            'body',
            'topic_slug',
            'image',
            'cta_label',
            'cta_url',
        ]

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
        return attrs

    def create(self, validated_data):
        return PinPromoCampaign.objects.create(
            owner=self.context['request'].user,
            pin=None,
            **validated_data,
        )
