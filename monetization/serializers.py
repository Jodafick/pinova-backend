from rest_framework import serializers

from .models import BoostPackage, PartnerCampaign


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
