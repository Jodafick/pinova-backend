"""Serializers API « Ads Manager » (assistant campagne / créatifs)."""

from rest_framework import serializers

from ads import constants as ac
from ads.models import Ad, AdCreative, AdTargeting, BusinessAccount, Campaign, CampaignBudget


def map_wizard_objective(raw: str) -> str:
    m = {
        'traffic': ac.CAMPAIGN_OBJECTIVE_TRAFFIC,
        'engagement': ac.CAMPAIGN_OBJECTIVE_ENGAGEMENT,
        'video_views': ac.CAMPAIGN_OBJECTIVE_AWARENESS,
        'conversions': ac.CAMPAIGN_OBJECTIVE_TRAFFIC,
        'awareness': ac.CAMPAIGN_OBJECTIVE_AWARENESS,
    }
    return m.get((raw or '').strip(), ac.CAMPAIGN_OBJECTIVE_AWARENESS)


def map_wizard_ad_format(creative_kind: str) -> str:
    k = (creative_kind or '').strip().lower()
    if k == 'image':
        return ac.AD_FORMAT_FEED_IMAGE
    if k == 'carousel':
        return ac.AD_FORMAT_FEED_IMAGE
    return ac.AD_FORMAT_FEED_VIDEO


class ManagerCampaignWriteSerializer(serializers.Serializer):
    business_account_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    objective = serializers.CharField(max_length=32, required=False, default='awareness')
    bid_strategy = serializers.ChoiceField(choices=ac.BID_STRATEGY_CHOICES, default=ac.BID_STRATEGY_CPM)
    bid_micro = serializers.IntegerField(min_value=0, default=0)
    start_at = serializers.DateTimeField(required=False, allow_null=True)
    end_at = serializers.DateTimeField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=ac.CAMPAIGN_STATUS_CHOICES,
        default=ac.CAMPAIGN_STATUS_DRAFT,
    )
    budget_type = serializers.ChoiceField(choices=ac.BUDGET_TYPE_CHOICES, default=ac.BUDGET_TYPE_DAILY)
    budget_micro = serializers.IntegerField(min_value=0)
    pacing = serializers.ChoiceField(choices=ac.PACING_CHOICES, default=ac.PACING_EVEN)

    def validate_business_account_id(self, value):
        user = self.context['request'].user
        if not BusinessAccount.objects.filter(id=value, owner=user).exists():
            raise serializers.ValidationError('Compte pub introuvable ou non autorisé.')
        return value

    def create(self, validated_data):
        ba_id = validated_data.pop('business_account_id')
        budget_type = validated_data.pop('budget_type')
        budget_micro = validated_data.pop('budget_micro')
        pacing = validated_data.pop('pacing')
        obj_raw = validated_data.pop('objective', 'awareness')
        validated_data['objective'] = map_wizard_objective(obj_raw)
        ba = BusinessAccount.objects.get(pk=ba_id)
        validated_data['business_account'] = ba
        campaign = Campaign.objects.create(**validated_data)
        CampaignBudget.objects.create(
            campaign=campaign,
            budget_type=budget_type,
            budget_micro=budget_micro,
            spend_micro=0,
            pacing=pacing,
        )
        return campaign


class ManagerCreativeWriteSerializer(serializers.ModelSerializer):
    business_account_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = AdCreative
        fields = (
            'business_account_id',
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
        extra_kwargs = {
            'headline': {'required': False, 'allow_blank': True},
            'body': {'required': False, 'allow_blank': True},
            'cta_text': {'required': False, 'allow_blank': True},
            'media_video_url': {'required': False, 'allow_blank': True},
        }

    def validate_business_account_id(self, value):
        user = self.context['request'].user
        if not BusinessAccount.objects.filter(id=value, owner=user).exists():
            raise serializers.ValidationError('Compte pub introuvable ou non autorisé.')
        return value

    def create(self, validated_data):
        ba_id = validated_data.pop('business_account_id')
        ba = BusinessAccount.objects.get(pk=ba_id)
        return AdCreative.objects.create(business_account=ba, **validated_data)


class AdTargetingWriteSerializer(serializers.Serializer):
    age_min = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=120)
    age_max = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=120)
    genders = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    countries = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    cities = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    languages = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    devices = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    operating_systems = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    interest_topic_slugs = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    interest_category_slugs = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    include_hashtags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    exclude_hashtags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    search_keywords = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    behavior_min_watch_7d_sec = serializers.IntegerField(required=False, allow_null=True)
    behavior_min_engagement_rate = serializers.DecimalField(
        max_digits=5, decimal_places=4, required=False, allow_null=True
    )
    recency_active_within_hours = serializers.IntegerField(required=False, allow_null=True)
    raw_rules = serializers.DictField(required=False, default=dict)


class ManagerAdWriteSerializer(serializers.Serializer):
    campaign_id = serializers.UUIDField()
    creative_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    ad_format = serializers.ChoiceField(choices=ac.AD_FORMAT_CHOICES, required=False)
    destination_url = serializers.CharField(required=False, allow_blank=True, default='', max_length=2048)
    deep_link = serializers.CharField(required=False, allow_blank=True, default='', max_length=512)
    status = serializers.ChoiceField(choices=ac.AD_STATUS_CHOICES, default=ac.AD_STATUS_DRAFT)
    creative_kind = serializers.CharField(required=False, allow_blank=True, default='video', write_only=True)
    targeting = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        user = self.context['request'].user
        camp = Campaign.objects.filter(pk=attrs['campaign_id'], business_account__owner=user).first()
        if not camp:
            raise serializers.ValidationError({'campaign_id': 'Campagne introuvable.'})
        cr = AdCreative.objects.filter(pk=attrs['creative_id'], business_account_id=camp.business_account_id).first()
        if not cr:
            raise serializers.ValidationError({'creative_id': 'Créatif introuvable pour ce compte.'})
        attrs['_campaign'] = camp
        attrs['_creative'] = cr
        if not attrs.get('ad_format'):
            attrs['ad_format'] = map_wizard_ad_format(attrs.get('creative_kind', 'video'))
        return attrs

    def create(self, validated_data):
        targeting_data = validated_data.pop('targeting', {}) or {}
        validated_data.pop('creative_kind', None)
        camp = validated_data.pop('_campaign')
        cr = validated_data.pop('_creative')
        validated_data.pop('campaign_id', None)
        validated_data.pop('creative_id', None)
        ad = Ad.objects.create(campaign=camp, creative=cr, **validated_data)
        tgt = AdTargetingWriteSerializer(data=targeting_data)
        tgt.is_valid(raise_exception=True)
        td = tgt.validated_data
        AdTargeting.objects.create(
            ad=ad,
            age_min=td.get('age_min'),
            age_max=td.get('age_max'),
            genders=td.get('genders') or [],
            countries=td.get('countries') or [],
            cities=td.get('cities') or [],
            languages=td.get('languages') or [],
            devices=td.get('devices') or [],
            operating_systems=td.get('operating_systems') or [],
            interest_topic_slugs=td.get('interest_topic_slugs') or [],
            interest_category_slugs=td.get('interest_category_slugs') or [],
            include_hashtags=td.get('include_hashtags') or [],
            exclude_hashtags=td.get('exclude_hashtags') or [],
            search_keywords=td.get('search_keywords') or [],
            behavior_min_watch_7d_sec=td.get('behavior_min_watch_7d_sec'),
            behavior_min_engagement_rate=td.get('behavior_min_engagement_rate'),
            recency_active_within_hours=td.get('recency_active_within_hours'),
            raw_rules=td.get('raw_rules') or {},
        )
        return ad
