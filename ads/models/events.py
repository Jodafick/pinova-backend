import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from ads import constants as ac
from ads.models.core import Ad


class AdImpression(models.Model):
    """Impression servie (avant / après filtre fraude selon is_valid)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ad_impressions',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='impressions')
    placement = models.CharField(max_length=24, choices=ac.PLACEMENT_CHOICES, db_index=True)
    served_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_valid = models.BooleanField(default=True, db_index=True)
    client_context = models.JSONField(
        default=dict,
        blank=True,
        help_text='app_version, surface, viewport, connection_type, etc.',
    )
    device_fingerprint_hash = models.CharField(max_length=128, blank=True, default='', db_index=True)
    ip_hash = models.CharField(max_length=128, blank=True, default='', db_index=True)
    fraud_flags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['ad', 'served_at'], name='ads_imp_ad_time_idx'),
            models.Index(fields=['user', 'served_at'], name='ads_imp_user_time_idx'),
            models.Index(fields=['placement', 'served_at'], name='ads_imp_pl_time_idx'),
            models.Index(fields=['request_id'], name='ads_imp_req_idx'),
        ]


class AdClick(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    impression = models.ForeignKey(
        AdImpression,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='clicks',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ad_clicks',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='clicks')
    clicked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    click_x = models.PositiveSmallIntegerField(null=True, blank=True)
    click_y = models.PositiveSmallIntegerField(null=True, blank=True)
    referrer = models.CharField(max_length=512, blank=True, default='')
    is_suspicious = models.BooleanField(default=False, db_index=True)
    suspicion_reasons = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['ad', 'clicked_at'], name='ads_clk_ad_time_idx'),
            models.Index(fields=['user', 'clicked_at'], name='ads_clk_user_time_idx'),
        ]


class AdView(models.Model):
    """Vue qualifiée (MRC-style : visible ≥1s, géré côté client + validation serveur)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    impression = models.ForeignKey(
        AdImpression,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='views',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ad_views',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='views')
    started_at = models.DateTimeField(db_index=True)
    duration_ms = models.PositiveIntegerField(default=0)
    visible_pct_max = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
    )
    completed = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['ad', 'started_at'], name='ads_view_ad_time_idx'),
            models.Index(fields=['user', 'started_at'], name='ads_view_user_time_idx'),
        ]


class AdWatchSession(models.Model):
    """Session de watch agrégée (ticks batchés depuis le client)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad_view = models.ForeignKey(
        AdView,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='watch_sessions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ad_watch_sessions',
    )
    ad = models.ForeignKey(Ad, on_delete=models.CASCADE, related_name='watch_sessions')
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    total_watched_ms = models.PositiveIntegerField(default=0)
    milestones = models.JSONField(
        default=dict,
        blank=True,
        help_text='p25, p50, p75, p100 timestamps ou compteurs.',
    )
    heartbeat_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['ad', 'started_at'], name='ads_ws_ad_start_idx'),
            models.Index(fields=['user', 'started_at'], name='ads_ws_user_start_idx'),
        ]


class AdDeliveryLog(models.Model):
    """Journal des décisions d’enchères / ranking pour audit et ML futur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ad_delivery_logs',
    )
    placement = models.CharField(max_length=24, choices=ac.PLACEMENT_CHOICES, db_index=True)
    candidates = models.JSONField(default=list, blank=True)
    scores = models.JSONField(default=dict, blank=True)
    chosen_ad = models.ForeignKey(
        Ad,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='delivery_logs',
    )
    reason = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['placement', 'created_at'], name='ads_dlog_pl_crt_idx'),
        ]


class AdPendingEvent(models.Model):
    """File d’attente pour batching async (impressions / vues / heartbeats)."""

    id = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=24, choices=ac.PENDING_EVENT_TYPE_CHOICES, db_index=True)
    payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=128, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')

    class Meta:
        indexes = [
            models.Index(fields=['processed_at', 'created_at'], name='ads_pend_proc_crt_idx'),
            models.Index(fields=['event_type', 'processed_at'], name='ads_pend_type_proc_idx'),
        ]
