import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from ads import constants as ac


class Advertiser(models.Model):
    """Annonceur (entité facturation / conformité)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    legal_name = models.CharField(max_length=255, blank=True, default='')
    tax_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    contact_email = models.EmailField(db_index=True)
    website = models.URLField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=ac.ADVERTISER_STATUS_CHOICES,
        default=ac.ADVERTISER_STATUS_PENDING,
        db_index=True,
    )
    billing_external_id = models.CharField(max_length=128, blank=True, default='', db_index=True)
    spam_strike_count = models.PositiveSmallIntegerField(default=0)
    suspended_until = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='ads_adv_stat_crt_idx'),
        ]

    def __str__(self):
        return self.name


class BusinessAccount(models.Model):
    """Compte pub lié à un utilisateur propriétaire et à un annonceur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ads_business_accounts',
    )
    advertiser = models.ForeignKey(
        Advertiser,
        on_delete=models.CASCADE,
        related_name='business_accounts',
    )
    display_name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default='UTC')
    currency = models.CharField(max_length=3, default='XOF')
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'advertiser'],
                name='ads_business_owner_adv_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['advertiser', 'is_active'], name='ads_biz_adv_act_idx'),
        ]

    def __str__(self):
        return f'{self.display_name} ({self.advertiser_id})'


class Campaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.CASCADE,
        related_name='campaigns',
    )
    name = models.CharField(max_length=255)
    objective = models.CharField(
        max_length=32,
        choices=ac.CAMPAIGN_OBJECTIVE_CHOICES,
        default=ac.CAMPAIGN_OBJECTIVE_AWARENESS,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ac.CAMPAIGN_STATUS_CHOICES,
        default=ac.CAMPAIGN_STATUS_DRAFT,
        db_index=True,
    )
    bid_strategy = models.CharField(
        max_length=8,
        choices=ac.BID_STRATEGY_CHOICES,
        default=ac.BID_STRATEGY_CPM,
    )
    bid_micro = models.BigIntegerField(
        default=0,
        help_text='En micro-unités monétaires (1/1_000_000) pour éviter les flottants.',
    )
    start_at = models.DateTimeField(null=True, blank=True, db_index=True)
    end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business_account', 'status'], name='ads_camp_ba_stat_idx'),
            models.Index(fields=['status', 'start_at', 'end_at'], name='ads_camp_win_idx'),
        ]

    def __str__(self):
        return self.name


class CampaignBudget(models.Model):
    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        related_name='budget',
    )
    budget_type = models.CharField(
        max_length=16,
        choices=ac.BUDGET_TYPE_CHOICES,
        default=ac.BUDGET_TYPE_DAILY,
    )
    budget_micro = models.BigIntegerField(default=0)
    spend_micro = models.BigIntegerField(default=0)
    pacing = models.CharField(
        max_length=16,
        choices=ac.PACING_CHOICES,
        default=ac.PACING_EVEN,
    )
    day_cursor = models.DateField(null=True, blank=True, db_index=True)
    spend_micro_day = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['day_cursor'], name='ads_cbudget_day_idx'),
        ]


class AdCategory(models.Model):
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=160)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Ad categories'
        ordering = ['slug']

    def __str__(self):
        return self.name


class AudienceSegment(models.Model):
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.CASCADE,
        related_name='audience_segments',
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    rules = models.JSONField(default=dict, help_text='DSL de ciblage réutilisable.')
    estimated_size = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business_account', 'name'], name='ads_seg_ba_name_idx'),
        ]

    def __str__(self):
        return self.name


class AdCreative(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_account = models.ForeignKey(
        BusinessAccount,
        on_delete=models.CASCADE,
        related_name='ad_creatives',
    )
    headline = models.CharField(max_length=255, blank=True, default='')
    body = models.TextField(blank=True, default='')
    cta_text = models.CharField(max_length=64, blank=True, default='')
    brand_name = models.CharField(max_length=128, blank=True, default='')
    brand_logo_url = models.URLField(blank=True, default='')
    media_image = models.ImageField(upload_to='ads/creatives/', null=True, blank=True)
    media_video_url = models.URLField(blank=True, default='')
    aspect_ratio = models.CharField(max_length=16, blank=True, default='9:16')
    autoplay_muted_default = models.BooleanField(
        default=True,
        help_text='Côté client : autoplay silencieux ; son uniquement après interaction.',
    )
    duration_seconds_est = models.PositiveSmallIntegerField(null=True, blank=True)
    categories = models.ManyToManyField(AdCategory, blank=True, related_name='creatives')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business_account', 'created_at'], name='ads_cr_ba_crt_idx'),
        ]


class Ad(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='ads')
    creative = models.ForeignKey(
        AdCreative,
        on_delete=models.PROTECT,
        related_name='ads',
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=ac.AD_STATUS_CHOICES,
        default=ac.AD_STATUS_DRAFT,
        db_index=True,
    )
    ad_format = models.CharField(
        max_length=32,
        choices=ac.AD_FORMAT_CHOICES,
        default=ac.AD_FORMAT_FEED_VIDEO,
        db_index=True,
    )
    destination_url = models.URLField(blank=True, default='')
    deep_link = models.CharField(max_length=512, blank=True, default='')
    priority_boost = models.SmallIntegerField(
        default=0,
        validators=[MinValueValidator(-50), MaxValueValidator(50)],
        help_text='Ajustement manuel léger (qualité organique reste prioritaire).',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['campaign', 'status'], name='ads_ad_camp_stat_idx'),
            models.Index(fields=['status', 'ad_format'], name='ads_ad_stat_fmt_idx'),
        ]

    def __str__(self):
        return self.name


class AdTargeting(models.Model):
    ad = models.OneToOneField(Ad, on_delete=models.CASCADE, related_name='targeting')
    age_min = models.PositiveSmallIntegerField(null=True, blank=True)
    age_max = models.PositiveSmallIntegerField(null=True, blank=True)
    genders = models.JSONField(default=list, blank=True)
    countries = models.JSONField(default=list, blank=True)
    cities = models.JSONField(
        default=list,
        blank=True,
        help_text='Liste normalisée: label, country_code, lat, lng, provider_place_id',
    )
    languages = models.JSONField(default=list, blank=True)
    devices = models.JSONField(default=list, blank=True)
    operating_systems = models.JSONField(default=list, blank=True)
    interest_topic_slugs = models.JSONField(default=list, blank=True)
    interest_category_slugs = models.JSONField(default=list, blank=True)
    behavior_min_watch_7d_sec = models.PositiveIntegerField(null=True, blank=True)
    behavior_min_engagement_rate = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True
    )
    recency_active_within_hours = models.PositiveIntegerField(null=True, blank=True)
    include_hashtags = models.JSONField(default=list, blank=True)
    exclude_hashtags = models.JSONField(default=list, blank=True)
    search_keywords = models.JSONField(default=list, blank=True)
    audience_segments = models.ManyToManyField(AudienceSegment, blank=True, related_name='targeted_ads')
    raw_rules = models.JSONField(default=dict, blank=True, help_text='Extensions / règles additionnelles.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['age_min', 'age_max'], name='ads_tgt_age_idx'),
        ]
