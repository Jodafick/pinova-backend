import uuid

from django.conf import settings
from django.db import models

from ads import constants as ac
from ads.models.core import Ad


class UserInterestScore(models.Model):
    """Scores d'intérêt par clé (topic, hashtag, catégorie, recherche) avec decay."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ad_interest_scores',
    )
    key_type = models.CharField(max_length=32, choices=ac.INTEREST_KEY_TYPE_CHOICES, db_index=True)
    key_slug = models.CharField(max_length=190, db_index=True)
    score = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    raw_score = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    source_counts = models.JSONField(default=dict, blank=True)
    last_signal_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'key_type', 'key_slug'],
                name='ads_interest_user_key_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'key_type', 'score'], name='ads_int_user_type_sc_idx'),
        ]


class UserBehaviorProfile(models.Model):
    """Profil comportemental agrégé pour ciblage et ranking."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ad_behavior_profile',
    )
    total_watch_seconds_7d = models.PositiveIntegerField(default=0)
    total_watch_seconds_30d = models.PositiveIntegerField(default=0)
    engagement_rate_30d = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    category_histogram = models.JSONField(default=dict, blank=True)
    hashtag_histogram = models.JSONField(default=dict, blank=True)
    search_histogram = models.JSONField(default=dict, blank=True)
    device_primary = models.CharField(max_length=32, blank=True, default='')
    os_primary = models.CharField(max_length=32, blank=True, default='')
    last_active_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ads_hidden_30d = models.PositiveIntegerField(default=0)
    ads_reported_30d = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['last_active_at'], name='ads_ubp_last_act_idx'),
        ]


class AdFrequencyTracking(models.Model):
    """Anti-répétition / caps par utilisateur et annonce."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ad_frequency_tracking',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='frequency_tracking')
    impressions_1h = models.PositiveSmallIntegerField(default=0)
    impressions_24h = models.PositiveIntegerField(default=0)
    impressions_7d = models.PositiveIntegerField(default=0)
    last_shown_at = models.DateTimeField(null=True, blank=True, db_index=True)
    rotation_bucket = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'ad'], name='ads_freq_user_ad_uniq'),
        ]
        indexes = [
            models.Index(fields=['user', 'last_shown_at'], name='ads_freq_user_last_idx'),
        ]


class UserTrustScore(models.Model):
    """Score de confiance anti-fraude (0–1)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ad_trust_score',
    )
    trust = models.DecimalField(max_digits=5, decimal_places=4, default=0.75)
    click_velocity_score = models.DecimalField(max_digits=5, decimal_places=4, default=1)
    impression_anomaly_score = models.DecimalField(max_digits=5, decimal_places=4, default=1)
    automation_flags = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
