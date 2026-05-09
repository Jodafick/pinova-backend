import uuid

from django.conf import settings
from django.db import models

from ads.models.core import Ad


class AdReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ad_reports',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='reports')
    reason = models.CharField(max_length=64, db_index=True)
    details = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['ad', 'created_at'], name='ads_rep_ad_crt_idx'),
        ]


class AdHide(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ad_hides',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='hides')
    reason = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'ad'], name='ads_hide_user_ad_uniq'),
        ]
        indexes = [
            models.Index(fields=['ad', 'created_at'], name='ads_hide_ad_crt_idx'),
        ]


class AdQualityScore(models.Model):
    """Quality score dynamique : mauvaises pubs perdent en diffusion."""

    ad = models.OneToOneField(Ad, on_delete=models.CASCADE, related_name='quality')
    quality_0_100 = models.PositiveSmallIntegerField(default=72)
    hide_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    report_rate = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    ctr_smoothed = models.DecimalField(max_digits=8, decimal_places=6, default=0)
    engagement_bonus = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    watch_bonus = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    penalty_hidden = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    penalty_reported = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['quality_0_100'], name='ads_qual_score_idx'),
        ]


class AdPerformanceSnapshot(models.Model):
    """Agrégats horaires / journaliers pour analytics scalable (tables de synthèse)."""

    GRANULARITY_HOUR = 'hour'
    GRANULARITY_DAY = 'day'
    GRANULARITY_CHOICES = [
        (GRANULARITY_HOUR, 'Hour'),
        (GRANULARITY_DAY, 'Day'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='performance_snapshots')
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField(db_index=True)
    granularity = models.CharField(max_length=8, choices=GRANULARITY_CHOICES, db_index=True)
    impressions = models.PositiveIntegerField(default=0)
    valid_impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    completes = models.PositiveIntegerField(default=0)
    spend_micro = models.BigIntegerField(default=0)
    watch_duration_ms_total = models.BigIntegerField(default=0)
    watch_duration_ms_avg = models.BigIntegerField(default=0)
    engagement_events = models.PositiveIntegerField(default=0)
    hidden_count = models.PositiveIntegerField(default=0)
    reported_count = models.PositiveIntegerField(default=0)
    ctr = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    cpm_micro = models.BigIntegerField(default=0)
    cpc_micro = models.BigIntegerField(default=0)
    engagement_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    retention_proxy = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['ad', 'period_start', 'granularity'],
                name='ads_perf_ad_period_gran_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['ad', 'granularity', 'period_start'], name='ads_perf_ad_gran_ps_idx'),
        ]
